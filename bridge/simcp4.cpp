// simcp4.dll - the SiMCP 4 GZCOM plugin for SimCity 4 Deluxe 1.1.641 (GOG digital edition)
//
// SimCity 4 loads every DLL in the root of the user Plugins folder as a GZCOM library: LoadLibrary, then
// GZDllGetGZCOMDirector() (loader at SC4 0x87BA7E), then director->InitializeCOM(pCOM, path) and OnStart(pCOM).
// SiMCP installs this DLL only in its own user folder (`-UserDir:`), never in the player's Plugins.
//
// The plugin is small and stable (the game keeps the file locked while it runs). It:
//   - checks the executable (TimeDateStamp 0x4C12BFB7) and stays inert on any other build;
//   - registers framework hooks in OnStart; in PostAppInit (main thread) gets cISC4App, the message server and the
//     command server and creates a message-only window on the main thread;
//   - loads the hot-reloadable inner bridge (simcp4bridge-<sha1>.dll, staged by the server) on request and forwards
//     command messages to it, every call under SEH so a fault returns status -100 and the game keeps running;
//   - publishes everything in the exported block g_simcp (read and written by the server with
//     ReadProcessMemory / WriteProcessMemory) and logs to simcp4.log next to itself.
//
// Interface slot orders are restated from the community's documentation of the GZCOM framework (gzcom-dll,
// sc4-gzids) and checked against 1.1.641; no third-party code is included.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stddef.h>

#define SC4_TIMESTAMP 0x4C12BFB7
#define SC4_BASE      0x400000

#define PLUG_MAGIC    0x50344353  // 'SC4P'
#define PLUG_VERSION  1
#define DIRECTOR_ID   0x7E3A9C41  // random, unique to SiMCP 4

#define WM_SIMCP          (WM_APP + 0x4C4)
#define WM_SIMCP_DEFERRED (WM_APP + 0x4C5)

enum { PLUG_PING = 1, PLUG_LOAD = 2, PLUG_UNLOAD = 3, PLUG_FIRST_BRIDGE_OP = 16 };

// GZCOM ids (sc4-gzids)
#define GZIID_cIGZUnknown          0x00000001
#define GZIID_cIGZCOMDirector      0xA21EE941
#define GZIID_cIGZFrameWorkHooks   0x03FA40BF
#define GZIID_cISC4App             0x26CE01C0
#define GZIID_cIGZMessageServer2   0x652294C7
#define GZSRVID_MessageServer2     0x04FA845B
#define GZIID_cIGZCommandServer    0xCB90253A
#define GZSRVID_CommandServer      0xEB903A32

// vtable slots used here (cIGZUnknown takes 0..2)
#define SLOT_QUERYINTERFACE       0
#define SLOT_RELEASE              2
#define SLOT_COM_FRAMEWORK        4   // cIGZCOM::FrameWork()
#define SLOT_FW_GETSYSTEMSERVICE  5   // cIGZFrameWork::GetSystemService(srvid, iid, void**)
#define SLOT_FW_ADDHOOK           7   // cIGZFrameWork::AddHook(cIGZFrameWorkHooks*)
#define SLOT_FW_REMOVEHOOK        8
#define SLOT_FW_APPLICATION       37  // cIGZFrameWork::Application() -> cIGZApp*

typedef DWORD (__stdcall *BridgeAttachFn)(void *plug);
typedef int (__stdcall *BridgeExecuteFn)(DWORD op);
typedef int (__stdcall *BridgeDeferredFn)(DWORD arg);
typedef void (__stdcall *BridgeDetachFn)(void);

#define LOG_SLOTS 64

#pragma pack(push, 4)
struct PlugBlock {
	DWORD magic;
	DWORD version;
	DWORD ready;          // 1 once PostAppInit ran and the window exists; 0xBAD: unsupported executable
	DWORD hwnd;           // message-only window on the main thread
	DWORD mainThreadId;
	DWORD layout[8];      // [0] sizeof [1] offsetof(bridgePath) [2] offsetof(log) [3] offsetof(hookCalls)
	DWORD pCOM;           // cIGZCOM*
	DWORD pFrameWork;     // cIGZFrameWork*
	DWORD pApp;           // cISC4App*
	DWORD pMsgServer;     // cIGZMessageServer2*
	DWORD pCmdServer;     // cIGZCommandServer*
	DWORD hookCalls[8];   // PreFrameWorkInit .. OnInstall
	DWORD inCall;         // a forwarded op is running (re-entrant calls are refused with -99)
	// inner bridge
	DWORD bridgeModule;
	DWORD bridgeBlock;    // what SimcpBridgeAttach returned (the inner bridge's own exported block)
	DWORD bridgeLoads;
	int bridgeStatus;     // result of the last load/unload (0 ok, <0 error; GetLastError in bridgeError)
	DWORD bridgeError;
	WCHAR bridgePath[MAX_PATH];  // written by the server before PLUG_LOAD
	// log ring (also mirrored to simcp4.log)
	DWORD logSeq;
	struct Entry { DWORD seq, tick, tid, what, a0, a1, a2; } log[LOG_SLOTS];
};
#pragma pack(pop)

extern "C" __declspec(dllexport) PlugBlock g_simcp = { PLUG_MAGIC, PLUG_VERSION };

enum {
	L_ATTACH = 1, L_GETDIRECTOR, L_INITCOM, L_ONSTART, L_ADDHOOK, L_HOOK, L_APP, L_SERVICES, L_WINDOW, L_LOAD,
	L_UNLOAD, L_FAULT, L_DETACH, L_BADEXE, L_QI,
};

static HMODULE g_hModule;
static HANDLE g_logFile = INVALID_HANDLE_VALUE;
static BridgeExecuteFn g_exec;
static BridgeDeferredFn g_deferred;
static BridgeDetachFn g_detach;

static void Log(DWORD what, DWORD a0 = 0, DWORD a1 = 0, DWORD a2 = 0) {
	DWORD seq = ++g_simcp.logSeq;
	PlugBlock::Entry *e = &g_simcp.log[(seq - 1) % LOG_SLOTS];
	e->tick = GetTickCount();
	e->tid = GetCurrentThreadId();
	e->what = what;
	e->a0 = a0;
	e->a1 = a1;
	e->a2 = a2;
	e->seq = seq;
	if (g_logFile != INVALID_HANDLE_VALUE) {
		static const char *names[] = { "?", "attach", "get-director", "initialize-com", "on-start", "add-hook", "hook",
			"app", "services", "window", "load-bridge", "unload-bridge", "fault", "detach", "unsupported-exe", "qi" };
		char line[200];
		int n = wsprintfA(line, "%lu tid=%lu %s %08lX %08lX %08lX\r\n", e->tick, e->tid,
			what < sizeof(names) / sizeof(names[0]) ? names[what] : "?", a0, a1, a2);
		DWORD w;
		WriteFile(g_logFile, line, n, &w, NULL);
	}
}

static void *VFn(void *obj, int slot) {
	return (*(void ***)obj)[slot];
}

static bool ExeIsSupported(void) {
	BYTE *base = (BYTE *)GetModuleHandleA(NULL);
	IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
	return (DWORD)(UINT_PTR)base == SC4_BASE && nt->FileHeader.TimeDateStamp == SC4_TIMESTAMP;
}

// ---------------------------------------------------------------------------
// Interfaces (MSVC thiscall vtables, as the game was built)

struct cIGZUnknown {
	virtual bool QueryInterface(DWORD iid, void **ppv) = 0;
	virtual DWORD AddRef() = 0;
	virtual DWORD Release() = 0;
};

struct cIGZFrameWorkHooks : cIGZUnknown {
	virtual bool PreFrameWorkInit() = 0;
	virtual bool PreAppInit() = 0;
	virtual bool PostAppInit() = 0;
	virtual bool PreAppShutdown() = 0;
	virtual bool PostAppShutdown() = 0;
	virtual bool PostSystemServiceShutdown() = 0;
	virtual bool AbortiveQuit() = 0;
	virtual bool OnInstall() = 0;
};

struct cIGZCOMDirector : cIGZUnknown {
	virtual bool InitializeCOM(void *pCOM, const void *libraryPath) = 0;  // 3
	virtual bool OnStart(void *pCOM) = 0;                                 // 4
	virtual void EnumClassObjects(void *callback, void *context) = 0;     // 5
	virtual bool GetClassObject(DWORD clsid, DWORD iid, void **ppv) = 0;  // 6
	virtual bool CanUnloadNow() = 0;                                      // 7
	virtual bool OnUnload() = 0;                                          // 8
	virtual DWORD RefCount() = 0;                                         // 9
	virtual DWORD RemoveRef() = 0;                                        // 10
	virtual void *FrameWork() = 0;                                        // 11
	virtual void *GZCOM() = 0;                                            // 12
	virtual DWORD GetDirectorID() const = 0;                              // 13
	virtual bool GetLibraryPath(void *outPath) = 0;                       // 14
	virtual DWORD GetHeapAllocatedSize() = 0;                             // 15
};

// ---------------------------------------------------------------------------
// The command window (main thread)

static int ForwardGuarded(DWORD op) {
	__try {
		return g_exec(op);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		Log(L_FAULT, op, GetExceptionCode());
		return -100;
	}
}

static int DeferredGuarded(DWORD arg) {
	__try {
		return g_deferred(arg);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		Log(L_FAULT, 0xDEF, GetExceptionCode());
		return -100;
	}
}

static void UnloadBridge(void) {
	if (!g_simcp.bridgeModule)
		return;
	if (g_detach) {
		__try { g_detach(); } __except (EXCEPTION_EXECUTE_HANDLER) { Log(L_FAULT, 0xDE7, GetExceptionCode()); }
	}
	Log(L_UNLOAD, g_simcp.bridgeModule);
	FreeLibrary((HMODULE)(UINT_PTR)g_simcp.bridgeModule);
	g_simcp.bridgeModule = 0;
	g_simcp.bridgeBlock = 0;
	g_exec = NULL;
	g_deferred = NULL;
	g_detach = NULL;
}

static int LoadBridge(void) {
	g_simcp.bridgePath[MAX_PATH - 1] = 0;
	UnloadBridge();
	HMODULE h = LoadLibraryW(g_simcp.bridgePath);
	if (!h) {
		g_simcp.bridgeError = GetLastError();
		return -2;
	}
	BridgeAttachFn attach = (BridgeAttachFn)GetProcAddress(h, "SimcpBridgeAttach");
	g_exec = (BridgeExecuteFn)GetProcAddress(h, "SimcpBridgeExecute");
	g_deferred = (BridgeDeferredFn)GetProcAddress(h, "SimcpBridgeRunDeferred");
	g_detach = (BridgeDetachFn)GetProcAddress(h, "SimcpBridgeDetach");
	if (!attach || !g_exec) {
		FreeLibrary(h);
		g_exec = NULL;
		return -3;
	}
	g_simcp.bridgeModule = (DWORD)(UINT_PTR)h;
	DWORD block = 0;
	__try {
		block = attach(&g_simcp);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		Log(L_FAULT, 0xA77, GetExceptionCode());
		UnloadBridge();
		return -100;
	}
	g_simcp.bridgeBlock = block;
	g_simcp.bridgeLoads++;
	Log(L_LOAD, (DWORD)(UINT_PTR)h, block);
	return 0;
}

static LRESULT CALLBACK PlugWndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
	if (msg == WM_SIMCP_DEFERRED) {
		// Not marked inCall: a modal loop inside this call keeps pumping, so bridge commands still work.
		return g_deferred ? DeferredGuarded((DWORD)wParam) : -98;
	}
	if (msg == WM_SIMCP) {
		DWORD op = (DWORD)wParam;
		if (g_simcp.inCall)
			return -99;  // re-entrant (a game modal loop is pumping messages inside an op)
		if (op == PLUG_PING)
			return (LRESULT)PLUG_MAGIC;
		if (op == PLUG_LOAD) {
			g_simcp.bridgeStatus = LoadBridge();
			return g_simcp.bridgeStatus;
		}
		if (op == PLUG_UNLOAD) {
			UnloadBridge();
			g_simcp.bridgeStatus = 0;
			return 0;
		}
		if (op >= PLUG_FIRST_BRIDGE_OP) {
			if (!g_exec)
				return -98;  // no inner bridge loaded
			g_simcp.inCall = 1;
			int st = ForwardGuarded(op);
			g_simcp.inCall = 0;
			return st;
		}
		return -1;
	}
	return DefWindowProcA(hWnd, msg, wParam, lParam);
}

static void CreatePlugWindow(void) {
	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.lpfnWndProc = PlugWndProc;
	wc.hInstance = g_hModule;
	wc.lpszClassName = "SiMCP4Plugin";
	if (!RegisterClassA(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
		return;
	HWND h = CreateWindowExA(0, wc.lpszClassName, "SiMCP 4", 0, 0, 0, 0, 0, HWND_MESSAGE, NULL, g_hModule, NULL);
	g_simcp.hwnd = (DWORD)(UINT_PTR)h;
	Log(L_WINDOW, g_simcp.hwnd);
}

// ---------------------------------------------------------------------------
// The director

class Director : public cIGZCOMDirector, public cIGZFrameWorkHooks {
public:
	DWORD refs;
	void *com;
	void *framework;
	bool supported;

	bool QueryInterface(DWORD iid, void **ppv) {
		if (!ppv)
			return false;
		if (iid == GZIID_cIGZUnknown || iid == GZIID_cIGZCOMDirector)
			*ppv = static_cast<cIGZCOMDirector *>(this);
		else if (iid == GZIID_cIGZFrameWorkHooks)
			*ppv = static_cast<cIGZFrameWorkHooks *>(this);
		else {
			Log(L_QI, iid);
			return false;
		}
		AddRef();
		return true;
	}
	DWORD AddRef() { return ++refs; }
	DWORD Release() { return refs ? --refs : 0; }  // static object: never deleted

	bool InitializeCOM(void *pCOM, const void *libraryPath) {
		Log(L_INITCOM, (DWORD)(UINT_PTR)pCOM, (DWORD)(UINT_PTR)libraryPath);
		supported = ExeIsSupported();
		if (!supported) {
			g_simcp.ready = 0xBAD;
			Log(L_BADEXE);
			return true;  // stay loaded but do nothing
		}
		com = pCOM;
		g_simcp.pCOM = (DWORD)(UINT_PTR)pCOM;
		return pCOM != NULL;
	}

	bool OnStart(void *pCOM) {
		Log(L_ONSTART, (DWORD)(UINT_PTR)pCOM);
		if (!supported || !pCOM)
			return true;
		__try {
			typedef void *(__thiscall *FrameWorkFn)(void *);
			framework = ((FrameWorkFn)VFn(pCOM, SLOT_COM_FRAMEWORK))(pCOM);
			g_simcp.pFrameWork = (DWORD)(UINT_PTR)framework;
			if (framework) {
				typedef bool (__thiscall *AddHookFn)(void *, cIGZFrameWorkHooks *);
				bool ok = ((AddHookFn)VFn(framework, SLOT_FW_ADDHOOK))(framework, static_cast<cIGZFrameWorkHooks *>(this));
				Log(L_ADDHOOK, (DWORD)(UINT_PTR)framework, ok);
			}
		}
		__except (EXCEPTION_EXECUTE_HANDLER) {
			Log(L_FAULT, 0x057, GetExceptionCode());
		}
		return true;
	}
	void EnumClassObjects(void *, void *) {}
	bool GetClassObject(DWORD, DWORD, void **) { return false; }
	bool CanUnloadNow() { return false; }
	bool OnUnload() { return true; }
	DWORD RefCount() { return refs; }
	DWORD RemoveRef() { return refs ? --refs : 0; }
	void *FrameWork() { return framework; }
	void *GZCOM() { return com; }
	DWORD GetDirectorID() const { return DIRECTOR_ID; }
	bool GetLibraryPath(void *) { return false; }
	DWORD GetHeapAllocatedSize() { return 0; }

	bool Hook(int i) {
		if (i >= 0 && i < 8)
			g_simcp.hookCalls[i]++;
		Log(L_HOOK, i);
		return true;
	}
	bool PreFrameWorkInit() { return Hook(0); }
	bool PreAppInit() { return Hook(1); }
	bool PostAppInit() {
		Hook(2);
		if (!supported || !framework)
			return true;
		g_simcp.mainThreadId = GetCurrentThreadId();
		__try {
			typedef void *(__thiscall *AppFn)(void *);
			typedef bool (__thiscall *QIFn)(void *, DWORD, void **);
			typedef bool (__thiscall *GetServiceFn)(void *, DWORD, DWORD, void **);
			void *app = ((AppFn)VFn(framework, SLOT_FW_APPLICATION))(framework);
			void *sc4app = NULL;
			if (app)
				((QIFn)VFn(app, SLOT_QUERYINTERFACE))(app, GZIID_cISC4App, &sc4app);
			g_simcp.pApp = (DWORD)(UINT_PTR)sc4app;
			Log(L_APP, (DWORD)(UINT_PTR)app, (DWORD)(UINT_PTR)sc4app);
			void *ms = NULL, *cs = NULL;
			((GetServiceFn)VFn(framework, SLOT_FW_GETSYSTEMSERVICE))(framework, GZSRVID_MessageServer2, GZIID_cIGZMessageServer2, &ms);
			((GetServiceFn)VFn(framework, SLOT_FW_GETSYSTEMSERVICE))(framework, GZSRVID_CommandServer, GZIID_cIGZCommandServer, &cs);
			g_simcp.pMsgServer = (DWORD)(UINT_PTR)ms;
			g_simcp.pCmdServer = (DWORD)(UINT_PTR)cs;
			Log(L_SERVICES, (DWORD)(UINT_PTR)ms, (DWORD)(UINT_PTR)cs);
		}
		__except (EXCEPTION_EXECUTE_HANDLER) {
			Log(L_FAULT, 0xA99, GetExceptionCode());
		}
		CreatePlugWindow();
		g_simcp.ready = g_simcp.hwnd ? 1 : 0;
		return true;
	}
	bool PreAppShutdown() {
		Hook(3);
		UnloadBridge();
		if (g_simcp.hwnd) {
			DestroyWindow((HWND)(UINT_PTR)g_simcp.hwnd);
			g_simcp.hwnd = 0;
		}
		g_simcp.ready = 0;
		return true;
	}
	bool PostAppShutdown() { return Hook(4); }
	bool PostSystemServiceShutdown() { return Hook(5); }
	bool AbortiveQuit() { return Hook(6); }
	bool OnInstall() { return Hook(7); }
};

static Director g_director;

extern "C" __declspec(dllexport) cIGZCOMDirector *GZDllGetGZCOMDirector(void) {
	Log(L_GETDIRECTOR, (DWORD)(UINT_PTR)&g_director);
	return &g_director;
}

static void OpenLog(void) {
	WCHAR path[MAX_PATH];
	DWORD n = GetModuleFileNameW(g_hModule, path, MAX_PATH);
	if (!n || n >= MAX_PATH - 16)
		return;
	WCHAR *slash = path + n;
	while (slash > path && slash[-1] != L'\\')
		slash--;
	lstrcpyW(slash, L"simcp4.log");
	g_logFile = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
	if (reason == DLL_PROCESS_ATTACH) {
		g_hModule = hinst;
		DisableThreadLibraryCalls(hinst);
		g_simcp.layout[0] = sizeof(PlugBlock);
		g_simcp.layout[1] = offsetof(PlugBlock, bridgePath);
		g_simcp.layout[2] = offsetof(PlugBlock, log);
		g_simcp.layout[3] = offsetof(PlugBlock, hookCalls);
		OpenLog();
		Log(L_ATTACH, (DWORD)(UINT_PTR)hinst, GetCurrentProcessId());
	}
	else if (reason == DLL_PROCESS_DETACH) {
		Log(L_DETACH);
		if (g_logFile != INVALID_HANDLE_VALUE)
			CloseHandle(g_logFile);
	}
	return TRUE;
}
