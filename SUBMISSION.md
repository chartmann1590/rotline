# Submitting Rotline to Depot

A person submits, not an agent. These are the steps for the publisher, Hartmann Studios, and only Charles sends it
for review.

## Packages

Depot takes one package per architecture. Each is built with the official Flatpak builder from the commit the
manifest pins, then installed and tested on that architecture.

- `com.charleshartmann.Rotline-1.0.0-x86_64.flatpak` for computers and TVs.
- `com.charleshartmann.Rotline-1.0.0-aarch64.flatpak` for phones, tablets and ARM computers.

Both are attached to the GitHub release [v1.0.0](https://github.com/chartmann1590/rotline/releases/tag/v1.0.0),
with `SHA256SUMS`.

> The bundles on the GitHub release are **GitHub builds**, built from `flatpak/github/`, and they offer updates from
> GitHub. For Depot, upload bundles built from `flatpak/com.charleshartmann.Rotline.json`, which update through
> Depot.

## Steps

1. **New app** `com.charleshartmann.Rotline`, named `Rotline`, in the `com.charleshartmann` namespace (the same as
   Hartmann Office, Earshot and Simmer). Category: Games.
2. **Packages:** both Depot-channel bundles, version `1.0.0`.
3. **Listing:** from `data/com.charleshartmann.Rotline.metainfo.xml`.
   - The description says what's free and what the optional one-time purchases are.
   - Privacy policy: `PRIVACY.md`.
   - In-app purchases: yes. Ads: none. Sign-in: none.
   - TV: supported, with input "controller" or "remote". It plays fully with arrows and OK.
   - Made with Godot 4.7.2. The package ships the official Godot Linux binary for its architecture, downloaded by the
     manifest and checked by SHA-256, with the game's pack. The pack is built from the pinned commit during the
     Flatpak build.
4. **Age rating (OARS):**
   - Cartoon violence: moderate.
   - Fantasy violence: moderate. The enemies are unrealistic human-like zombies.
   - Bloodshed: mild. It's unrealistic: dark red splats with no gore detail.
   - Money purchasing: intense, because real money can be spent in the game.
   - Nothing else applies: no chat, no user content, no gambling and no random rewards.
5. **Permissions** Depot will show:
   - Uses the internet: the store's prices and purchases, and update checks. Playing needs no connection.
   - Plays audio: sound effects and music. Luma's list shows this as "Records audio" because
     `--socket=pulseaudio` is the only way a Flatpak plays sound. No microphone is used.
   - Graphics: `--device=dri` for OpenGL. The lights and shadows are drawn on the GPU.
6. **Screenshots:** `screenshots/`, covering a computer, a phone and a TV.
7. **Review.** Only Charles sends it for review.

## Review notes (for the reviewer)

- **Purchases (3.4 and 3.6).**
  - Every item is a one-time unlock: two chapters, a weapon pack, a character pack, and a bundle of all four.
  - Prices come from the license server and are never written in the code.
  - Nothing is pre-selected or counted down.
  - The panel says before anything is sent that checkout is run by Stripe, where the email goes, and that nothing
    renews.
  - The game has no virtual currency for sale, no loot boxes or random rewards, and no energy or timers to skip.
    Scrap, used for upgrades, is earned only by playing.
  - Chapter 1, Endless and all upgrades are free. Nothing that was free becomes paid.
- **No advertising (2.3).** No ad SDKs, no advertising identifiers and no analytics.
- **Controls.**
  - Keyboard and mouse, two touch sticks with buttons, and the TV keys (arrows, OK, Back) that the shell makes from a
    remote or a gamepad.
  - `X-Luma-TV-Presentation=tv`, so a gamepad drives it in TV posture. Without a mouse, aiming and firing are
    automatic.
  - The game doesn't ask for `--device=input`. A pad works through the shell's TV keys, so nothing needs a newer
    Flatpak.
- **Keeping the screen on.** While a level is being played, Godot asks the system to keep the screen awake. It lets
  go when you leave the level.
- **Flashing light.** Downtown has lightning. It can be turned off in Settings ("Lightning flashes").
- **Updates (1.3).** The Depot build updates through Depot. The app shows release notes from GitHub but never
  downloads anything there.

## Billing (the store)

Rotline uses the shared Hartmann Studios license server (`livecaptionn-premium`, `/v2` API) and Stripe Checkout,
the same system as Earshot, Hartmann Office and Simmer. There is no Stripe key in the app.

Product keys, and the proposed prices (pending Charles's approval):

| Product key | Label | Stripe mode | Price |
| --- | --- | --- | --- |
| `rotline_chapter2` | Chapter 2: Downtown | payment | $1.99 once |
| `rotline_chapter3` | Chapter 3: The Harbor | payment | $1.99 once |
| `rotline_arsenal` | Arsenal | payment | $0.99 once |
| `rotline_survivors` | Survivors | payment | $0.99 once |
| `rotline_complete` | Complete pack | payment | $3.99 once, implies the four above |

**Status:** registration is still needed. `/v2/catalog?app=rotline` answers `404 Unknown app` until the studio's
billing maintainer registers it. Until then, the store page says purchases aren't open yet, Chapter 1 and Endless
play as normal, and nothing breaks. The app also treats the Complete pack as including the other four, so it works
whether or not the server expands `implies`. The registration request is in `TAB-ROTLINE-STRIPE-20261120.md`, kept
beside the repos rather than in them.
