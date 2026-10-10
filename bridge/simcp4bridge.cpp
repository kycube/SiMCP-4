// simcp4bridge.dll - the hot-reloadable inner bridge of SiMCP 4 (SimCity 4 Deluxe 1.1.641)
//
// Loaded and unloaded by the plugin (simcp4.dll) on the game's main thread, from a content-addressed copy the
// server stages in %TEMP%\simcp4, so rebuilding never needs a game restart and never meets a locked file.
// The server writes a request into the exported block g_bridge (WriteProcessMemory) and sends WM_SIMCP with the
// op number to the plugin's window; the plugin calls SimcpBridgeExecute(op) on the main thread under SEH.
// Calls that may open a modal window are run deferred: posted to the plugin's window and executed from the game's
// message loop, so the bridge stays responsive while the game waits for an answer.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#define BRIDGE_MAGIC   0x42344353  // 'SC4B'
#define BRIDGE_VERSION 1
#define WM_SIMCP_DEFERRED (WM_APP + 0x4C5)

enum {
	OP_PING = 16,
	OP_CALL = 17,      // args: fn, conv (bit 1: returns float), nargs (0..12), this (0 = cdecl/stdcall), a0..a11 -> ret[0]=eax ret[1]=edx ret[2]=float bits
	OP_CALL_SEQ = 18,  // args: count; str: CallDesc[count] run back-to-back in one main-thread turn -> ret[i] = eax
	OP_DEFER = 19,     // args as OP_CALL: run later from the message loop; state.defer* report the outcome
	OP_COMMAND = 20,   // args: defer (0/1); str: a game command line ("LoadRegion Timbuktu") -> ret[0] = the command's
	                   // status (0 ok, 2 unknown command / bad parameters), ret[1] = output length; out = output text
	OP_STEP_DAYS = 21, // args: days, max ms (0 = 250), max steps (0 = 5000) -> ret[0] days done, ret[1] steps,
	                   // ret[2] day number, ret[3] idle passes, ret[4] one-shots pending, ret[5] 1 = day in progress;
	                   // the simulator must be hidden-paused (see re/reports/time)
};

// Game addresses (SimCity 4 1.1.641; re/reports/commands and re/reports/time REPORT.md)
#define FN_RZSTRING_CTOR   0x578390   // cRZString::cRZString() (thiscall)
#define SLOT_RZSTRING_DEL  28         // cRZString scalar deleting destructor (flag 0 = in place)
#define CS_CREATE_PARAMS   5          // cIGZCommandServer::CreateCommandParameterSet(cIGZCommandParameterSet**)
#define CS_EXECUTE_STRING  19         // ExecuteCommand(char const*, uint32 len, cIGZCommandParameterSet* out)
#define CS_OUTPUT_TO_TEXT  24         // ConvertCommandOutputToString(cIGZCommandParameterSet*, cIGZString&)
#define G_SIMULATOR        0xB43D5C   // cSC4Simulator* of the open city
#define FN_SIM_ADVANCE     0x702A80   // cSC4Simulator::AdvanceTime (thiscall, no args)
#define FN_SIM_RUN_AGENTS  0x7038B0   // cSC4Simulator::RunAgents (thiscall, no args)
#define FN_TIMER_RESTART   0x89058F   // cRZTimer::Restart (thiscall) - the simulator's agent budget timer at S+0x198
#define FN_SIM_RUN_IDLE    0x702DF0   // cSC4Simulator::RunIdle (thiscall, no args; skipped while hidden-paused)
#define PLUG_CMDSERVER_IDX 17         // PlugBlock::pCmdServer as a DWORD index

// One call of an OP_CALL_SEQ batch (packed into BridgeBlock::str).
// nargs bits: 0..7 count (0..6); 8..13 arg j is an address to read the actual dword from at call time;
// 14 `this` is such an address; 15 `fn` is a vtable slot index of `this`; 16 store EAX into the next call's arg 0
// (chains getters: obj = a->GetB(); obj->GetC() ...).
struct CallDesc {
	DWORD fn;
	DWORD thisPtr;
	int nargs;
	int args[6];
};

#pragma pack(push, 4)
struct BridgeBlock {
	DWORD magic;
	DWORD version;
	DWORD layout[8];      // [0] sizeof [1] offsetof(seq) [2] offsetof(str) [3] offsetof(doneSeq) [4] offsetof(state)
	DWORD plug;           // the plugin's PlugBlock
	DWORD module;
	// request
	DWORD seq;
	DWORD op;
	int args[16];
	char str[1024];
	// response
	DWORD doneSeq;
	int status;           // 0 ok, <0 error (-100 crash caught)
	int ret[16];
	DWORD msgLen;
	char msg[2048];
	// persistent state
	struct State {
		DWORD deferPosted;
		DWORD deferDone;
		int deferStatus;
		int deferRet;
		DWORD reserved[12];
	} state;
	DWORD outLen;
	char out[4096];       // text output of the last command (OP_COMMAND, immediate or deferred)
	char scratch[8192];   // the server's working memory for call arguments (points, vectors, strings, outputs)
	// the virtual pointer: until the tick count pickActive (GetTickCount; 0 = off), the city view's PickTerrain
	// answers pickPos (world metres) instead of the real cursor, so the game's own tools act on a cell SiMCP
	// chooses (the real mouse never moves; the deadline frees the player's mouse even if SiMCP stops mid-action)
	DWORD pickActive;
	float pickPos[3];
	DWORD pickHits;
	DWORD pickInstalled;
	DWORD faults;         // exceptions caught inside game code since this bridge loaded (the game may be inconsistent)
	DWORD pickOccupant;   // while the pointer is active: the cISC4Occupant* PickOccupant answers (0 = the real one)
};
#pragma pack(pop)

extern "C" __declspec(dllexport) BridgeBlock g_bridge = { BRIDGE_MAGIC, BRIDGE_VERSION };

// Undecorated export names for the plugin's GetProcAddress (x86 __stdcall names are decorated as _Name@N).
#pragma comment(linker, "/EXPORT:SimcpBridgeAttach=_SimcpBridgeAttach@4")
#pragma comment(linker, "/EXPORT:SimcpBridgeExecute=_SimcpBridgeExecute@4")
#pragma comment(linker, "/EXPORT:SimcpBridgeRunDeferred=_SimcpBridgeRunDeferred@4")
#pragma comment(linker, "/EXPORT:SimcpBridgeDetach=_SimcpBridgeDetach@0")

static HMODULE g_hModule;
static DWORD *g_plug;      // PlugBlock (only fields at fixed offsets are used: hwnd at +12)
static int g_lastEdx;

static void Msg(const char *fmt, ...);

static struct {
	int kind;            // 0 call, 1 command
	DWORD fn, thisPtr;
	int nargs;
	int args[8];
	char text[1024];
} g_defer;

static void *VSlot(void *obj, int slot) {
	return (*(void ***)obj)[slot];
}

// Runs a command line through the game's command server; its text output goes to g_bridge.out.
static int RunCommandText(const char *text) {
	g_bridge.outLen = 0;
	g_bridge.out[0] = 0;
	void *cs = g_plug ? (void *)(UINT_PTR)g_plug[PLUG_CMDSERVER_IDX] : NULL;
	if (!cs)
		return -4;
	void *params = NULL;
	typedef bool (__thiscall *CreateFn)(void *, void **);
	((CreateFn)VSlot(cs, CS_CREATE_PARAMS))(cs, &params);
	if (!params)
		return -5;
	typedef int (__thiscall *ExecFn)(void *, const char *, DWORD, void *);
	int r = ((ExecFn)VSlot(cs, CS_EXECUTE_STRING))(cs, text, (DWORD)strlen(text), params);
	DWORD str[8];        // a cRZString (0x14 bytes) made by the game's own constructor
	memset(str, 0, sizeof(str));
	typedef void (__thiscall *CtorFn)(void *);
	((CtorFn)FN_RZSTRING_CTOR)(str);
	typedef bool (__thiscall *ConvFn)(void *, void *, void *);
	((ConvFn)VSlot(cs, CS_OUTPUT_TO_TEXT))(cs, params, str);
	const char *b = (const char *)(UINT_PTR)str[1], *e = (const char *)(UINT_PTR)str[2];
	if (b && e > b) {
		DWORD n = (DWORD)(e - b);
		if (n > sizeof(g_bridge.out) - 1)
			n = sizeof(g_bridge.out) - 1;
		memcpy(g_bridge.out, b, n);
		g_bridge.out[n] = 0;
		g_bridge.outLen = n;
	}
	typedef void (__thiscall *DelFn)(void *, DWORD);
	((DelFn)VSlot(str, SLOT_RZSTRING_DEL))(str, 0);   // frees the text with the game's allocator
	typedef DWORD (__thiscall *ReleaseFn)(void *);
	((ReleaseFn)VSlot(params, 2))(params);
	return r;
}

// True when every agent list (one-shot .. year, types 0..9) has run to its end for the current day.
static bool ListsFinished(BYTE *S) {
	for (int t = 0; t < 10; t++)
		if (*(DWORD *)(S + 0x1B0 + 4 * t) != *(DWORD *)(S + 0x114 + 12 * t))
			return false;
	return true;
}

// Advances the simulation by whole days with the game's own day code (re/reports/time REPORT.md section 4).
static int StepDays(int days, DWORD maxMs, int maxSteps, int idlePerDay, int *r) {
	BYTE *S = (BYTE *)(UINT_PTR)*(DWORD *)G_SIMULATOR;
	if (!S) {
		Msg("no city simulator");
		return -6;
	}
	if (!S[0x2C] || S[0x2D]) {
		Msg("the simulator is not initialised or is running its tick");
		return -7;
	}
	if (*(int *)(S + 0x34) <= 0) {
		Msg("hidden-pause the simulator first");
		return -8;
	}
	// Each step is the pair the game's own tick runs: AdvanceTime (starts the next day once every agent list has
	// finished the current one and hour >= 24; clears the event flags) then RunAgents (runs the agents of the events
	// that fired; time-sliced agents return "not done" and are called again on the next step). A day counts when its
	// date has started and all its lists have finished. Some agents wait for work done outside the simulator (after a
	// city loads, for a few seconds), so a call never spins: it stops after maxSteps steps or maxMs and reports the
	// day in progress; the caller lets the game's main loop run and calls again (verified live 2026-10-08).
	typedef void (__thiscall *SimFn)(void *);
	DWORD t0 = GetTickCount();
	int done = 0, steps = 0, idles = 0, blocked = 0;
	DWORD k = *(DWORD *)(S + 0x80), budget = *(DWORD *)(S + 0x78);
	// The wall-clock day throttle (AdvanceTime needs S+0x80 ms on timer S+0x48 since the last day) is lifted while
	// stepping by setting ms-per-day to 0; RunAgents works until its budget timer S+0x198 passes S+0x78 ms, so the
	// timer is restarted before each call (the game's tick does the same) with a 50 ms budget. Both restored below.
	*(DWORD *)(S + 0x80) = 0;
	*(DWORD *)(S + 0x78) = 50;
	while (done < days && steps < maxSteps && GetTickCount() - t0 < maxMs) {
		bool inProgress = !ListsFinished(S);
		DWORD d0 = *(DWORD *)(S + 0xEC);
		((SimFn)FN_SIM_ADVANCE)(S);
		((SimFn)FN_TIMER_RESTART)(S + 0x198);
		((SimFn)FN_SIM_RUN_AGENTS)(S);
		steps++;
		bool advanced = *(DWORD *)(S + 0xEC) != d0;
		if (inProgress || advanced) {
			blocked = 0;
			if (ListsFinished(S)) {
				done++;
				// The game's own loop runs its idle agents between days (construction finishing, power and water
				// networks, growth bookkeeping); give them the same passes with the hidden pause lifted.
				for (int i = 0; i < idlePerDay; i++) {
					int hidden = *(int *)(S + 0x34);
					*(int *)(S + 0x34) = 0;
					((SimFn)FN_SIM_RUN_IDLE)(S);
					*(int *)(S + 0x34) = hidden;
					idles++;
				}
			}
			continue;
		}
		// Nothing moved: one-shot agents (queued right after a city loads) hold the clock - AdvanceTime returns at
		// once while any is registered - and finish only with the game's idle work, so give them one idle pass.
		if (*(DWORD *)(S + 0x118) > 0) {
			int hidden = *(int *)(S + 0x34);
			*(int *)(S + 0x34) = 0;
			((SimFn)FN_SIM_RUN_IDLE)(S);
			*(int *)(S + 0x34) = hidden;
			idles++;
		}
		else if (++blocked >= 1000) {
			Msg("the day does not advance (hour %u)", *(DWORD *)(S + 0xBC));
			break;
		}
	}
	*(DWORD *)(S + 0x80) = k;
	*(DWORD *)(S + 0x78) = budget;
	r[0] = done;
	r[1] = steps;
	r[2] = (int)*(DWORD *)(S + 0xEC);
	r[3] = idles;
	r[4] = (int)*(DWORD *)(S + 0x118);   // one-shot agents still registered
	r[5] = ListsFinished(S) ? 0 : 1;      // 1: a day is in progress (call again after the game's loop has run)
	return 0;
}

static void Msg(const char *fmt, ...) {
	if (g_bridge.msgLen >= sizeof(g_bridge.msg) - 2)
		return;
	va_list ap;
	va_start(ap, fmt);
	int n = _vsnprintf(g_bridge.msg + g_bridge.msgLen, sizeof(g_bridge.msg) - 1 - g_bridge.msgLen, fmt, ap);
	va_end(ap);
	if (n > 0)
		g_bridge.msgLen += n;
	g_bridge.msg[g_bridge.msgLen] = 0;
}

static float g_lastFloat;

// floatRet: the function returns float / double in ST0 (popped into g_lastFloat); only for such functions, since
// popping an empty x87 stack would leave the FPU in a fault state.
// A call target must be code the game or a DLL loaded (committed, executable image memory), and a `this` pointer
// readable memory: a stale object or a garbage vtable slot then fails cleanly instead of jumping into the game. (A
// fault inside game code, even caught, can leave a simulator mid-update - the suspect behind the Phase 3 stall.)
static bool CodeAddress(DWORD fn) {
	MEMORY_BASIC_INFORMATION mbi;
	if (!fn || !VirtualQuery((LPCVOID)(UINT_PTR)fn, &mbi, sizeof(mbi)))
		return false;
	const DWORD exec = PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
	return mbi.State == MEM_COMMIT && mbi.Type == MEM_IMAGE && (mbi.Protect & exec) && !(mbi.Protect & PAGE_GUARD);
}

static bool ReadableAddress(DWORD p) {
	MEMORY_BASIC_INFORMATION mbi;
	if (p < 0x10000 || !VirtualQuery((LPCVOID)(UINT_PTR)p, &mbi, sizeof(mbi)))
		return false;
	const DWORD rd = PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE |
	                 PAGE_EXECUTE_WRITECOPY;
	return mbi.State == MEM_COMMIT && (mbi.Protect & rd) && !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS));
}

static int g_guardRefused = 0;

static int __declspec(noinline) CallGeneric(DWORD fn, DWORD thisPtr, int nargs, const int *a, bool floatRet = false) {
	int result, hi;
	float fr = 0.0f;
	__asm {
		mov esi, a
		mov ecx, nargs
		mov edi, esp
	push_loop:
		test ecx, ecx
		jz do_call
		dec ecx
		push dword ptr [esi + ecx * 4]
		jmp push_loop
	do_call:
		mov ecx, thisPtr
		call fn
		mov esp, edi
		mov result, eax
		mov hi, edx
		cmp floatRet, 0
		je no_float
		fstp fr
	no_float:
	}
	g_lastEdx = hi;
	g_lastFloat = fr;
	return result;
}

static int CallSequence(int n) {
	int maxn = (int)(sizeof(g_bridge.str) / sizeof(CallDesc));
	if (n < 0 || n > maxn) {
		Msg("call sequence must have 0..%d entries", maxn);
		return -1;
	}
	CallDesc *d = (CallDesc *)g_bridge.str;
	int carry = 0;
	bool haveCarry = false;
	for (int i = 0; i < n; i++) {
		int cnt = d[i].nargs & 0xFF;
		if (cnt > 6) cnt = 6;
		int ind = (d[i].nargs >> 8) & 0x3F;
		DWORD th = (d[i].nargs & (1 << 14)) ? *(DWORD *)d[i].thisPtr : d[i].thisPtr;
		if (haveCarry && th == 0xFFFFFFFF)
			th = (DWORD)carry;   // `this` = the previous call's result
		if ((d[i].nargs & (1 << 15)) && !th) {
			Msg("call %d: null this", i);
			g_bridge.ret[0] = i;
			return -2;
		}
		if ((d[i].nargs & (1 << 15)) && (!ReadableAddress(th) || !ReadableAddress(*(DWORD *)th))) {
			Msg("call %d: this %08lX is not a live object", i, th);
			g_bridge.ret[0] = i;
			g_guardRefused++;
			return -4;
		}
		DWORD fn = (d[i].nargs & (1 << 15)) ? (*(DWORD **)th)[d[i].fn] : d[i].fn;
		if (!CodeAddress(fn) || (th && !ReadableAddress(th))) {
			Msg("call %d: %08lX is not code (this %08lX)", i, fn, th);
			g_bridge.ret[0] = i;
			g_guardRefused++;
			return -4;
		}
		int args[6];
		for (int j = 0; j < 6; j++)
			args[j] = ((ind >> j) & 1) ? *(int *)d[i].args[j] : d[i].args[j];
		int r = CallGeneric(fn, th, cnt, args);
		if (i < 16)
			g_bridge.ret[i] = r;
		carry = r;
		haveCarry = true;
	}
	return 0;
}

static int Execute(DWORD op) {
	int *a = g_bridge.args;
	int *r = g_bridge.ret;
	switch (op) {
	case OP_PING:
		r[0] = BRIDGE_VERSION;
		r[1] = (int)GetCurrentThreadId();
		r[2] = (int)(UINT_PTR)g_hModule;
		r[3] = g_guardRefused;           // calls refused by the address guard since the bridge loaded
		return 0;
	case OP_CALL:
		if (!CodeAddress((DWORD)a[0]) || ((a[1] & 1) && !ReadableAddress((DWORD)a[3]))) {
			Msg("refused: %08lX is not code, or this %08lX is not a live object", (DWORD)a[0], (DWORD)a[3]);
			g_guardRefused++;
			return -4;
		}
		r[0] = CallGeneric((DWORD)a[0], (DWORD)a[3], a[2] < 0 ? 0 : (a[2] > 12 ? 12 : a[2]), &a[4], (a[1] & 2) != 0);
		r[1] = g_lastEdx;
		r[2] = *(int *)&g_lastFloat;   // with conv bit 1: the float result
		return 0;
	case OP_CALL_SEQ:
		return CallSequence(a[0]);
	case OP_DEFER: {
		if (g_bridge.state.deferDone != g_bridge.state.deferPosted) {
			Msg("a deferred call is still running");
			return -3;
		}
		if (!CodeAddress((DWORD)a[0]) || ((a[1] & 1) && !ReadableAddress((DWORD)a[3]))) {
			Msg("refused: %08lX is not code, or this %08lX is not a live object", (DWORD)a[0], (DWORD)a[3]);
			g_guardRefused++;
			return -4;
		}
		g_defer.kind = 0;
		g_defer.fn = (DWORD)a[0];
		g_defer.thisPtr = (DWORD)a[3];
		g_defer.nargs = a[2] < 0 ? 0 : (a[2] > 8 ? 8 : a[2]);
		memcpy(g_defer.args, &a[4], sizeof(g_defer.args));
		g_bridge.state.deferPosted++;
		PostMessageA((HWND)(UINT_PTR)g_plug[3], WM_SIMCP_DEFERRED, 0, 0);
		r[0] = (int)g_bridge.state.deferPosted;
		return 0;
	}
	case OP_COMMAND: {
		g_bridge.str[sizeof(g_bridge.str) - 1] = 0;
		if (!a[0]) {
			r[0] = RunCommandText(g_bridge.str);
			r[1] = (int)g_bridge.outLen;
			return 0;
		}
		if (g_bridge.state.deferDone != g_bridge.state.deferPosted) {
			Msg("a deferred call is still running");
			return -3;
		}
		g_defer.kind = 1;
		memcpy(g_defer.text, g_bridge.str, sizeof(g_defer.text));
		g_bridge.state.deferPosted++;
		PostMessageA((HWND)(UINT_PTR)g_plug[3], WM_SIMCP_DEFERRED, 0, 0);
		r[0] = (int)g_bridge.state.deferPosted;
		return 0;
	}
	case OP_STEP_DAYS:
		return StepDays(a[0], a[1] ? (DWORD)a[1] : 250, a[2] ? a[2] : 5000, a[3] < 0 ? 0 : a[3], r);
	}
	Msg("unknown op %u", op);
	return -1;
}

// cISC4View3DWin vtable slot 36 PickTerrain(int screenX, int screenZ, float *worldOut, bool stopAtWater) and
// slot 37 PickOccupant(int screenX, int screenZ, cISC4Occupant **out) (the occupant comes back AddRef'd)
#define VIEW_PICK_SLOT_ADDR 0xABCED0
#define FN_VIEW_PICK        0x7E5840
#define VIEW_PICKOCC_SLOT_ADDR 0xABCED4
#define FN_VIEW_PICKOCC     0x7E5890
static DWORD g_pickOrig, g_pickOccOrig;

static bool PickActive(void) {
	return g_bridge.pickActive && (int)(g_bridge.pickActive - GetTickCount()) > 0;
}

static bool __fastcall PickOccHook(void *self, void *edx, int sx, int sz, void **out) {
	if (PickActive() && g_bridge.pickOccupant && out) {
		void *occ = (void *)(UINT_PTR)g_bridge.pickOccupant;
		typedef DWORD (__thiscall *AddRefFn)(void *);
		((AddRefFn)(*(DWORD **)occ)[1])(occ);
		*out = occ;
		g_bridge.pickHits++;
		return true;
	}
	typedef bool (__fastcall *PickOccFn)(void *, void *, int, int, void **);
	return ((PickOccFn)g_pickOccOrig)(self, edx, sx, sz, out);
}

static bool __fastcall PickHook(void *self, void *edx, int sx, int sz, float *out, bool stopAtWater) {
	if (PickActive() && out) {
		out[0] = g_bridge.pickPos[0];
		out[1] = g_bridge.pickPos[1];
		out[2] = g_bridge.pickPos[2];
		g_bridge.pickHits++;
		return true;
	}
	typedef bool (__fastcall *PickFn)(void *, void *, int, int, float *, bool);
	return ((PickFn)g_pickOrig)(self, edx, sx, sz, out, stopAtWater);
}

static void SetVSlot(DWORD addr, DWORD value) {
	DWORD *slot = (DWORD *)addr, old;
	if (VirtualProtect(slot, 4, PAGE_EXECUTE_READWRITE, &old)) {
		*slot = value;
		VirtualProtect(slot, 4, old, &old);
		FlushInstructionCache(GetCurrentProcess(), slot, 4);
	}
}

static void InstallPickHook(void) {
	// only over the game's own functions (never over another hook)
	if (*(DWORD *)VIEW_PICK_SLOT_ADDR == FN_VIEW_PICK && *(DWORD *)VIEW_PICKOCC_SLOT_ADDR == FN_VIEW_PICKOCC) {
		g_pickOrig = FN_VIEW_PICK;
		g_pickOccOrig = FN_VIEW_PICKOCC;
		SetVSlot(VIEW_PICK_SLOT_ADDR, (DWORD)(UINT_PTR)&PickHook);
		SetVSlot(VIEW_PICKOCC_SLOT_ADDR, (DWORD)(UINT_PTR)&PickOccHook);
		g_bridge.pickInstalled = 1;
	}
}

static void RemovePickHook(void) {
	g_bridge.pickActive = 0;
	g_bridge.pickOccupant = 0;
	if (g_bridge.pickInstalled) {
		if (*(DWORD *)VIEW_PICK_SLOT_ADDR == (DWORD)(UINT_PTR)&PickHook)
			SetVSlot(VIEW_PICK_SLOT_ADDR, g_pickOrig);
		if (*(DWORD *)VIEW_PICKOCC_SLOT_ADDR == (DWORD)(UINT_PTR)&PickOccHook)
			SetVSlot(VIEW_PICKOCC_SLOT_ADDR, g_pickOccOrig);
	}
	g_bridge.pickInstalled = 0;
}

// ---- crash log: faults in the game's code go to <SiMCP home>\crash.log (SIMCP4_HOME, else %USERPROFILE%\SiMCP-4)
// - the game exits silently on a crash, so this is the only trace. A vectored handler notes first-chance faults
// raised outside the bridge's guarded calls (the game or a plugin may still handle them: "first-chance"); the
// guards' own filters note the faults they catch ("caught").
static PVOID g_veh;
static volatile LONG g_inBridgeCall;
static volatile LONG g_crashBusy;
static int g_crashLogged, g_caughtLogged;
// what the bridge was running when a fault was caught: the op, and its command line or call target
static volatile DWORD g_curOp, g_curFn;
static const char *volatile g_curText;

static void CrashLog(EXCEPTION_POINTERS *ep, const char *kind) {
	char path[MAX_PATH + 32];
	DWORD n = GetEnvironmentVariableA("SIMCP4_HOME", path, MAX_PATH);
	if (n && n < MAX_PATH) {
		lstrcatA(path, "\\crash.log");
	} else {
		n = GetEnvironmentVariableA("USERPROFILE", path, MAX_PATH);
		if (!n || n >= MAX_PATH)
			return;
		lstrcatA(path, "\\SiMCP-4\\crash.log");
	}
	HANDLE h = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
	if (h == INVALID_HANDLE_VALUE)
		return;
	char buf[2048];
	SYSTEMTIME t;
	GetLocalTime(&t);
	EXCEPTION_RECORD *er = ep->ExceptionRecord;
	CONTEXT *c = ep->ContextRecord;
	int len = _snprintf(buf, sizeof(buf) - 1,
		"%04d-%02d-%02d %02d:%02d:%02d pid %lu %s exception 0x%08lX at 0x%08lX (%s 0x%08lX) eax %08lX ebx %08lX "
		"ecx %08lX edx %08lX esi %08lX edi %08lX ebp %08lX esp %08lX\r\n  stack:",
		t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond, GetCurrentProcessId(), kind, er->ExceptionCode,
		(DWORD)(UINT_PTR)er->ExceptionAddress, er->NumberParameters >= 2 && er->ExceptionInformation[0] ? "writing" : "reading",
		er->NumberParameters >= 2 ? (DWORD)er->ExceptionInformation[1] : 0, c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi,
		c->Ebp, c->Esp);
	// scan the stack only within this thread's own stack (TEB StackLimit .. StackBase): no faulting reads here
	NT_TIB *tib = (NT_TIB *)NtCurrentTeb();
	DWORD lo = (DWORD)(UINT_PTR)tib->StackLimit, hi = (DWORD)(UINT_PTR)tib->StackBase;
	DWORD sp = c->Esp;
	int found = 0;
	if (sp >= lo && sp < hi) {
		for (DWORD a = sp & ~3u; a + 4 <= hi && a < sp + 1024 && found < 16 && len < (int)sizeof(buf) - 16; a += 4) {
			DWORD v = *(DWORD *)(UINT_PTR)a;
			if (v >= 0x401000 && v < 0xA80000) {     // a return address into SimCity 4.exe (probably)
				len += _snprintf(buf + len, sizeof(buf) - 1 - len, " %08lX", v);
				found++;
			}
		}
	}
	len += _snprintf(buf + len, sizeof(buf) - 1 - len, "\r\n");
	if (kind[0] == 'c' && len < (int)sizeof(buf) - 200) {      // caught-in-call / caught-in-deferred: what ran
		len += _snprintf(buf + len, sizeof(buf) - 1 - len, "  op %lu fn %08lX%s%.120s\r\n", g_curOp, g_curFn,
		                 g_curText ? " command " : "", g_curText ? g_curText : "");
	}
	DWORD w;
	WriteFile(h, buf, len, &w, NULL);
	CloseHandle(h);
}

static bool IsFault(DWORD code) {
	return code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_ILLEGAL_INSTRUCTION ||
	       code == EXCEPTION_INT_DIVIDE_BY_ZERO || code == EXCEPTION_PRIV_INSTRUCTION ||
	       code == EXCEPTION_ARRAY_BOUNDS_EXCEEDED || code == EXCEPTION_STACK_OVERFLOW;
}

static LONG CALLBACK CrashVeh(EXCEPTION_POINTERS *ep) {
	DWORD code = ep->ExceptionRecord->ExceptionCode;
	if (IsFault(code) && code != EXCEPTION_STACK_OVERFLOW && !g_inBridgeCall && g_crashLogged < 20 &&
	    !InterlockedExchange(&g_crashBusy, 1)) {
		g_crashLogged++;
		CrashLog(ep, "first-chance");
		InterlockedExchange(&g_crashBusy, 0);
	}
	return EXCEPTION_CONTINUE_SEARCH;
}

// filter for the bridge's guards: note the fault (a few per load), then handle it
static int LogCaught(EXCEPTION_POINTERS *ep, const char *kind) {
	if (IsFault(ep->ExceptionRecord->ExceptionCode) && ep->ExceptionRecord->ExceptionCode != EXCEPTION_STACK_OVERFLOW &&
	    g_caughtLogged < 50 && !InterlockedExchange(&g_crashBusy, 1)) {
		g_caughtLogged++;
		CrashLog(ep, kind);
		InterlockedExchange(&g_crashBusy, 0);
	}
	return EXCEPTION_EXECUTE_HANDLER;
}

extern "C" __declspec(dllexport) DWORD __stdcall SimcpBridgeAttach(void *plug) {
	g_plug = (DWORD *)plug;
	InstallPickHook();
	if (!g_veh)
		g_veh = AddVectoredExceptionHandler(1, CrashVeh);
	g_bridge.plug = (DWORD)(UINT_PTR)plug;
	g_bridge.module = (DWORD)(UINT_PTR)g_hModule;
	return (DWORD)(UINT_PTR)&g_bridge;
}

extern "C" __declspec(dllexport) int __stdcall SimcpBridgeExecute(DWORD op) {
	g_bridge.msgLen = 0;
	g_bridge.msg[0] = 0;
	memset(g_bridge.ret, 0, sizeof(g_bridge.ret));
	int status;
	InterlockedIncrement(&g_inBridgeCall);
	g_curOp = op;
	g_curFn = (op == OP_CALL) ? (DWORD)g_bridge.args[0] : 0;
	g_bridge.str[sizeof(g_bridge.str) - 1] = 0;
	g_curText = (op == OP_COMMAND) ? g_bridge.str : NULL;
	__try {
		status = Execute(op);
	}
	__except (LogCaught(GetExceptionInformation(), "caught-in-call")) {
		Msg("exception 0x%08X while executing op %u", GetExceptionCode(), op);
		g_bridge.faults++;
		status = -100;
	}
	InterlockedDecrement(&g_inBridgeCall);
	g_bridge.status = status;
	g_bridge.doneSeq = g_bridge.seq;
	return status;
}

extern "C" __declspec(dllexport) int __stdcall SimcpBridgeRunDeferred(DWORD) {
	int status = 0;
	g_curOp = g_defer.kind == 1 ? OP_COMMAND : OP_DEFER;
	g_curFn = g_defer.kind == 1 ? 0 : g_defer.fn;
	g_curText = g_defer.kind == 1 ? g_defer.text : NULL;
	__try {
		if (g_defer.kind == 1)
			g_bridge.state.deferRet = RunCommandText(g_defer.text);
		else
			g_bridge.state.deferRet = CallGeneric(g_defer.fn, g_defer.thisPtr, g_defer.nargs, g_defer.args);
	}
	__except (LogCaught(GetExceptionInformation(), "caught-in-deferred")) {
		g_bridge.faults++;
		status = -100;
	}
	g_bridge.state.deferStatus = status;
	g_bridge.state.deferDone = g_bridge.state.deferPosted;
	return status;
}

extern "C" __declspec(dllexport) void __stdcall SimcpBridgeDetach(void) {
	RemovePickHook();
	if (g_veh) {
		RemoveVectoredExceptionHandler(g_veh);
		g_veh = NULL;
	}
	g_plug = NULL;
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
	if (reason == DLL_PROCESS_ATTACH) {
		g_hModule = hinst;
		DisableThreadLibraryCalls(hinst);
		g_bridge.layout[0] = sizeof(BridgeBlock);
		g_bridge.layout[1] = offsetof(BridgeBlock, seq);
		g_bridge.layout[2] = offsetof(BridgeBlock, str);
		g_bridge.layout[3] = offsetof(BridgeBlock, doneSeq);
		g_bridge.layout[4] = offsetof(BridgeBlock, state);
		g_bridge.layout[5] = offsetof(BridgeBlock, out);
		g_bridge.layout[6] = offsetof(BridgeBlock, scratch);
		g_bridge.layout[7] = offsetof(BridgeBlock, pickActive);
	}
	return TRUE;
}
