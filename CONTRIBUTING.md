# Contributing

Thanks for helping make Rotline better.

## Reporting a problem

[Open an issue](https://github.com/chartmann1590/rotline/issues/new/choose) and say what you did, what happened, and
which level and controls you were using.

## Sending a change

1. Fork the repository and make a branch.
2. Keep each pull request to one change.
3. Run the checks:
   ```sh
   python3 -m pytest tests/test_game.py tests/test_billing.py tests/test_promo.py tests/test_updates.py
   xvfb-run flatpak run --command=python3 org.projectluma.Sdk//44 tests/test_ui.py
   luma lint && luma test
   ```
4. Play what you changed with a keyboard and mouse, with touch at phone width (360 px), and with arrows and Return
   only (that's how a TV remote and a gamepad arrive).
5. Say in the pull request what you tested.

## Style

- `game.py`, `levels.py`, `progress.py` and `catalog.py` don't import GTK, so they can be tested anywhere. Keep it
  that way. The world never draws or plays sound: it appends events, and the window turns them into both.
- A new level needs a map that passes `test_every_map_is_sound` and `test_everything_on_every_map_can_be_reached`.
- Use LumaUI parts (`luma_appkit`) for everything outside a level, and Luma's colour tokens there.
- Words in the interface are short and plain, in sentence case.
- The store sells one-time unlocks only. No coins, no timers, no random rewards, and nothing that makes the free game
  worse.

By contributing you agree your work is licensed under GPL-3.0-or-later.
