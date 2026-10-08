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
	OP_CALL = 17,      // args: fn, conv (unused), nargs (0..12), this (0 = cdecl/stdcall), a0..a11 -> ret[0]=eax ret[1]=edx
	OP_CALL_SEQ = 18,  // args: count; str: CallDesc[count] run back-to-back in one main-thread turn -> ret[i] = eax
	OP_DEFER = 19,     // args as OP_CALL: run later from the message loop; state.defer* report the outcome
	OP_COMMAND = 20,   // args: defer (0/1); str: a game command line ("LoadRegion Timbuktu") -> ret[0] = the command's
	                   // status (0 ok, 2 unknown command / bad parameters), ret[1] = output length; out = output text
	OP_STEP_DAYS = 21, // args: days, max ms (0 = 250), max steps (0 = 5000) -> ret[0] days done, ret[1] steps,
	                   // ret[2] day number, ret[3] idle passes, ret[4] one-shots pending, ret[5] 1 = day in progress;
	                   // the simulator must be hidden-paused (see re/agents/time)
};

// Game addresses (SimCity 4 1.1.641; re/agents/commands and re/agents/time REPORT.md)
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

// Advances the simulation by whole days with the game's own day code (re/agents/time REPORT.md section 4).
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

static int __declspec(noinline) CallGeneric(DWORD fn, DWORD thisPtr, int nargs, const int *a) {
	int result, hi;
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
	}
	g_lastEdx = hi;
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
		DWORD fn = (d[i].nargs & (1 << 15)) ? (*(DWORD **)th)[d[i].fn] : d[i].fn;
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
		return 0;
	case OP_CALL:
		r[0] = CallGeneric((DWORD)a[0], (DWORD)a[3], a[2] < 0 ? 0 : (a[2] > 12 ? 12 : a[2]), &a[4]);
		r[1] = g_lastEdx;
		return 0;
	case OP_CALL_SEQ:
		return CallSequence(a[0]);
	case OP_DEFER: {
		if (g_bridge.state.deferDone != g_bridge.state.deferPosted) {
			Msg("a deferred call is still running");
			return -3;
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

// cISC4View3DWin vtable slot 36 PickTerrain(int screenX, int screenZ, float *worldOut, bool stopAtWater)
#define VIEW_PICK_SLOT_ADDR 0xABCED0
#define FN_VIEW_PICK        0x7E5840
static DWORD g_pickOrig;

static bool __fastcall PickHook(void *self, void *edx, int sx, int sz, float *out, bool stopAtWater) {
	if (g_bridge.pickActive && (int)(g_bridge.pickActive - GetTickCount()) > 0 && out) {
		out[0] = g_bridge.pickPos[0];
		out[1] = g_bridge.pickPos[1];
		out[2] = g_bridge.pickPos[2];
		g_bridge.pickHits++;
		return true;
	}
	typedef bool (__fastcall *PickFn)(void *, void *, int, int, float *, bool);
	return ((PickFn)g_pickOrig)(self, edx, sx, sz, out, stopAtWater);
}

static void SetPickSlot(DWORD value) {
	DWORD *slot = (DWORD *)VIEW_PICK_SLOT_ADDR, old;
	if (VirtualProtect(slot, 4, PAGE_EXECUTE_READWRITE, &old)) {
		*slot = value;
		VirtualProtect(slot, 4, old, &old);
		FlushInstructionCache(GetCurrentProcess(), slot, 4);
	}
}

static void InstallPickHook(void) {
	DWORD cur = *(DWORD *)VIEW_PICK_SLOT_ADDR;
	if (cur == FN_VIEW_PICK) {           // only over the game's own function (never over another hook)
		g_pickOrig = cur;
		SetPickSlot((DWORD)(UINT_PTR)&PickHook);
		g_bridge.pickInstalled = 1;
	}
}

static void RemovePickHook(void) {
	g_bridge.pickActive = 0;
	if (g_bridge.pickInstalled && *(DWORD *)VIEW_PICK_SLOT_ADDR == (DWORD)(UINT_PTR)&PickHook)
		SetPickSlot(g_pickOrig);
	g_bridge.pickInstalled = 0;
}

extern "C" __declspec(dllexport) DWORD __stdcall SimcpBridgeAttach(void *plug) {
	g_plug = (DWORD *)plug;
	InstallPickHook();
	g_bridge.plug = (DWORD)(UINT_PTR)plug;
	g_bridge.module = (DWORD)(UINT_PTR)g_hModule;
	return (DWORD)(UINT_PTR)&g_bridge;
}

extern "C" __declspec(dllexport) int __stdcall SimcpBridgeExecute(DWORD op) {
	g_bridge.msgLen = 0;
	g_bridge.msg[0] = 0;
	memset(g_bridge.ret, 0, sizeof(g_bridge.ret));
	int status;
	__try {
		status = Execute(op);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		Msg("exception 0x%08X while executing op %u", GetExceptionCode(), op);
		g_bridge.faults++;
		status = -100;
	}
	g_bridge.status = status;
	g_bridge.doneSeq = g_bridge.seq;
	return status;
}

extern "C" __declspec(dllexport) int __stdcall SimcpBridgeRunDeferred(DWORD) {
	int status = 0;
	__try {
		if (g_defer.kind == 1)
			g_bridge.state.deferRet = RunCommandText(g_defer.text);
		else
			g_bridge.state.deferRet = CallGeneric(g_defer.fn, g_defer.thisPtr, g_defer.nargs, g_defer.args);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		g_bridge.faults++;
		status = -100;
	}
	g_bridge.state.deferStatus = status;
	g_bridge.state.deferDone = g_bridge.state.deferPosted;
	return status;
}

extern "C" __declspec(dllexport) void __stdcall SimcpBridgeDetach(void) {
	RemovePickHook();
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
