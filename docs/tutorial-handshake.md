# Tutorial: Two-Character Handshake

1. Open a sample project or create two character instances in one scene.
2. Keep the scene to two actors; domain validation, API validation, and UI scope reject larger casts.
3. Add a visible target object such as a door if you want shared gaze after the contact.
4. Open **Motion** and enter:

```text
Mira approaches Jon, shakes his right hand, then they both look toward the door.
```

5. Inspect the action cards for actor ownership, synchronization, and hand contact.
6. Compile the plan.
7. Check the clip markers for `contact` and `sync`, then scrub the hold interval.

Expected result: the scheduler creates a shared timeline, the compiler maintains contact within tolerance for the handshake phase, and the final clip remains editable without another model call.
