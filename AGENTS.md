# AGENTS.md - Mio3 UV Maya Port Rehberi

Bu klasor, Blender referans eklentisinden Maya 2022-2024 icin sifirdan yazilan Python/PySide2 portudur.

## Mimari

- `mio3_uv_maya/core/`: Maya mesh ve UV veri modeli. Maya API importlari lazy yapilir.
- `mio3_uv_maya/operators/`: UI butonlarina baglanan operator aileleri.
- `mio3_uv_maya/ui/`: `workspaceControl` ve PySide2 panel.
- `mio3_uv_maya/assets/`: ikonlar ve checker map dosyalari.
- `install/`: Maya module ve userSetup bootstrap dosyalari.

## Temel Kararlar

- Hedef Maya surumu: 2022-2024.
- UI: dockable `workspaceControl`.
- Qt: PySide2.
- Mesh/UV API: once `maya.api.OpenMaya.MFnMesh`, gerekli yerde `maya.cmds`.
- Blender `UVIslandManager` ve `UVNodeManager` fikirleri Maya icin yeniden yazilir; Blender BMesh API'si taklit edilmez.

## Gelistirme Kurallari

- Maya disinda import edilebilir core modul yazmaya calis; Maya bagimli kodu `core/maya_api.py` arkasindan lazy import et.
- Her operator undo chunk icinde calismali.
- Global Maya node cleanup sadece `mio3UvMaya_` prefix'li owned node'lara dokunmali.
- Blender referans algoritmasindan port edilen kodlarda lisans/atif notlarini koru.
- Yeni operator eklerken `operators/base.py` icindeki `Action` modeliyle UI'a bagla.
- Tamamlanmamis parity davranisini sessizce basarili gosterme; kullaniciya warning ver.

## Test

- Repo icinde syntax icin `python3 -m compileall Maya-Addon` calistirilabilir.
- Gercek davranis Maya 2022, 2023 ve 2024 icinde test edilmelidir.
- Minimum Maya smoke test: module load, `mio3_uv_maya.show()`, panel dock/close, Normalize, Align, Checker Map, undo/redo.

