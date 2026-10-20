# Simulator validation — 17 October 2026

Historical local checks carried forward from the motion document. These were
not rerun during documentation consolidation and do not validate the current
archive deployment or model services. Current behavior is in the
[simulator reference](../reference/simulator.md).

## Browser cost

The user canceled the animal-model replacement. The demo retains its original
procedural cat/deer and improves their motor coordination. This update adds no generated
animal model, animal model-loading pipeline or external animal asset requirement.

Only the selected species is created when needed, and exactly one animal is
visible. Repeated tree geometry/materials are shared, gait is distance-driven,
and scene resources are disposed on teardown. These are implementation choices,
not an FPS guarantee. In a post-cleanup local headless Chrome sample, the
original cat used 23 meshes/1,356 triangles and returned to its anchor in
2.09 s; the deer used 24 meshes/1,320 triangles and returned in 2.01 s. The
full scene, including the upstream duck, ran at about 60 FPS with 133–137 draw
calls and approximately 200,500 rendered triangles. Both motor checks had no
page errors. These are isolated measurements, not a browser/device guarantee.

## Verification record, 17 October 2026

- The final six-action adapter sequence included roaming, approach before every primitive, `head_nod`, `sit_cycle`, `ground_pick`, `short_walk`, `head_scan`, `stand_hold`, and repeated-Stop cancellation during sitting and nodding.
- Physics time advanced continuously from 1.56 to 45.56 s. No reset or recovery occurred. Observed X stayed between -0.670 and 0.465 m; Y stayed between -0.278 and 0.047 m.
- The complete sit gesture took about 5.32 s without approach. Its trunk moved from roughly 0.116 m down to 0.059 m and returned. A nod took about 2.77 s including settling and covered approximately 0.52–0.53 rad of actual head pitch.
- Cancellation testing initially exposed a repeated-walk hand-back problem that triggered recovery; the adapter fix was retested successfully with Stop, Stop and immediate preparation. The failed intermediate run is not counted as a success.
- The isolated native-policy audit exercised both kicks and one roll without recovery/reset, but did not establish them as bounded evidence actions. They remain disabled.
- 21 adapter tests pass. The combined frontend suite, including animal motor changes, reports 45 tests and a successful production build; the backend suite reports 163 tests. Real-time measurements above came from the local Chrome/MuJoCo test session, not a physical robot or a latency benchmark.
- Earlier navigation checks covered fresh reset followed by 11.5 s and 30 s of search-time roaming, approach and actions without recovery/reset. The tightened interior route leaves room for the pretrained controller's turning radius.

Development-only adapter hooks were used for physics measurements. These checks validate execution and cancellation, not the correctness of wildlife captions or a human review of footage. Normal UI, animal-renderer and live archive verification remain separate checks.
