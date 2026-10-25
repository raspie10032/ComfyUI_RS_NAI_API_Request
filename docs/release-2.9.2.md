# 2.9.2

Released source update dated 2026-10-25.

- Add shared RS/NAI character/context interoperability and preserve backend-specific settings through round trips.
- Add interactive camera captions, reproducible random views, optional distance/roll synchronization and flat-plane mask perspective.
- Set direction and height independently from the centre of each diagram to the pointer. Both pipe sockets use `building_pipe`; old `context` API inputs and saved UI connections remain supported.
- Collect independent building roles in any order before Finalize; apply pending camera settings once at Finalize. Repeated settings intentionally use the last applicable value.
- Keep Position editing active through camera/reference nodes and include downstream roles on an unbranched chain. Position edits pre-camera geometry; Finalize previews the transformed layout.

## Compatibility and limits

Update both extensions together for shared local building/mask features. Finalize is the boundary of order-independent assembly. Repeated settings and replacing all masks are explicit overrides. Branches retain their own placement editor. Linked numeric inputs and unresolved masks require their source values first.

Camera captions guide generation; they do not enforce a 3D camera or pose. Perspective transforms a flat mask plane and rejects edge-on angles. NAI uses transformed character centres, not silhouette masks. Native NAI-only camera use does not require the local sampler; editing local mask records requires it. Generation settings and strict no-Anlas protection remain owned by the downstream generator.

## Validation

The preceding camera/building implementation was verified with 5,040 Python role orders, 10,080 JavaScript role orders and 24 real ComfyUI executor graphs. Installed UI checks covered 24 orders and both camera entries with mask/box dragging, scaling, undo and workflow restoration. The recorded native-runtime regression suites passed: local 277 passed / 1 skipped, NAI 310 passed. These are pipeline/UI checks, not a new image-quality benchmark. Earlier limited image trials and their model-dependent limits are described in the [camera guide](camera-control.md).

This version update changes package metadata and release documentation. No additional generation request or Anlas spending is required for the version bump.

**한국어:** 카메라·공통 컨텍스트·순서 무관 빌딩 파이프 수정을 묶은 업데이트입니다. 같은 항목을 여러 번 설정하면 마지막 값이 우선합니다. 카메라 뒤에서도 위치·마스크를 편집할 수 있으며 Finalize에서 카메라를 한 번 적용합니다. 양쪽 확장을 함께 업데이트한 뒤 ComfyUI를 재시작하고 브라우저를 새로고침하세요.

Version-update verification: local Python 278 tests (277 passed, 1 skipped); NAI Python 310 passed with the real local package and ComfyUI runtime available; all 15 local and 14 NAI JavaScript test files passed. The camera raster parity test used the ComfyUI Python through `CAMERA_PYTHON`. Package/README version consistency and local documentation links were checked.
