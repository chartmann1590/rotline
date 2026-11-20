# Contributing

Thanks for helping make Rotline better.

## Reporting a problem

[Open an issue](https://github.com/chartmann1590/rotline/issues/new/choose) and say what you did, what happened, and
which level and controls you were using.

## Sending a change

1. Fork the repository and make a branch. Open `game/` in the Godot 4.7 editor.
2. Keep each pull request to one change.
3. Run the checks:
   ```sh
   ROTLINE_TEST=all godot --headless --fixed-fps 60 --path game
   GODOT=godot python3 tests/test_store.py
   luma lint && luma test
   ```
4. Play what you changed:
   - with a keyboard and mouse;
   - with touch at phone width (360 px);
   - with arrows and Return only, which is how a TV remote and a gamepad arrive.
5. Say in the pull request what you tested.

## Style

- **The art and sound are made in code.** Change `tools/make_art.py` or `tools/make_sounds.py` and run it again,
  rather than editing the PNGs or WAVs. Run `make_art.py` with Python and pycairo (the Luma SDK has both). No stock
  or AI-generated assets.
- **Levels.** A new level needs a map that passes `maps_are_sound` and `everything_can_be_reached` in
  `game/tests/run_tests.gd`. A free level must stay winnable by the test bot.
- **Words.** Words in the game are short and plain, in sentence case. Titles are capitals in Bebas Neue.
- **The store** sells one-time unlocks only: no coins, no timers, no random rewards, and nothing that makes the free
  game worse.

By contributing you agree your work is licensed under GPL-3.0-or-later.
