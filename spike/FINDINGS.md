# Phase 0 spike — findings

Game build: `27.0.0.2493426` (Steam, early access), macOS 26.1 (25B78), arm64, SIP enabled.

## Baseline (Task 1 Step 1, 2026-11-07)

```
codesign --verify --deep --strict --verbose=2 ".../Football Manager 27/fm.app"
fm.app: valid on disk
fm.app: satisfies its Designated Requirement
```

## Toolchain (Task 1 Step 2)

- .NET SDK `8.0.427` at `~/.dotnet` (dotnet-install.sh, channel 8.0)
- Rosetta 2: already installed

## Loader review (Task 1 Step 4)

Package: `FM27-BepInEx-macOS-arm64.zip` (sptndc base + FM27 patches by "hasan"), 237 files,
sha256 `c9789aba5fcb5391cd8904bee5bb6b57b9485b1aeb5a20e434c3af38db70eb43`, dated 2026-10-30.
Extracted to `~/fm-spike-vendor/sptndc/FM27-BepInEx/`.

| Part | Verdict |
|---|---|
| `run_fm27_bepinex.sh` | Read fully. No sudo/csrutil/network. Original `fm.app` only read (`cp -cR` APFS clone into `FM27-BepInEx/shadow/`); ad-hoc re-sign + thinning only on the clone. Clears quarantine only in its own folder. Launch via `/usr/bin/arch -arm64 -e DYLD_INSERT_LIBRARIES=…` for the game process only. OK. |
| `source/fm27_doorstop.c` | Read fully. dyld-interposes `dlsym`, swaps `il2cpp_init`, starts CoreCLR, calls `Doorstop.Entrypoint.Start`. No file/network beyond its log. OK. **Rebuilt from source locally** (clang, ad-hoc) → sha256 `4d9a599a…8424`; prebuilt kept as `fm27_doorstop.prebuilt.dylib`, not used. |
| `source/FM27HookFix/FM27HookFix.cs` | Read relevant parts. Harmony finalizer on Il2CppInterop hook lookup; only writes `BepInEx/config/fm27_hookfix.cfg`. Prebuilt DLL used (not rebuilt). |
| `dotnet/` | Official Microsoft .NET runtime 6.0.7 (dylibs signed TeamIdentifier `UBF8T346G9` = Microsoft). OK. |
| `libdobby.dylib`, `libcapstone.dylib` | Ad-hoc signed community builds, no source in package (capstone has build script). **Unverified.** |
| `BepInEx/core/*.dll` (modified BepInEx 6, Il2CppInterop) | sptndc's modified builds, upstream forks show no published diff. **Unverified.** |
| First launch | Per README, BepInEx downloads Unity base libraries once (standard BepInEx IL2CPP behavior). |

Residual risk: unverified community binaries run inside the FM27 process with the user's permissions.

## Criterion 1 — loader running: **PASS** (2026-11-07, build 27.0.0.2493426)

- Steam launch option: `".../Football Manager 27/FM27-BepInEx/run_fm27_bepinex.sh" %command%`
- `fm27_doorstop.log`: `il2cpp_init intercepted` → `CoreCLR started` → `Doorstop.Entrypoint.Start() returned` (~42 s first launch).
- `LogOutput.log`: `Chainloader startup complete`. FM27 Hook Fix resolved `GenericMethod::GetMethod` → `GameAssembly+0x7063D8`; warning `Class::Init signatures have been exhausted, using a substitute!` (non-fatal).
- `BepInEx/interop/`: 182 DLLs incl. SI.Bindable, SI.Bindable.Reference.Core, SI.Core, SI.UI, FM.UI, FM.GamePlugin, UnityEngine.UIElementsModule.
- Original `fm.app` signature after run: `codesign --verify --deep --strict` → valid (unchanged).
