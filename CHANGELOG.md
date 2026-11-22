# Changelog

## 1.0.1 (2026-11-21)

- **Fairer Tank fights.** In 2-4 Rooftop Signal and 3-4 The Ferry the Tanks used to arrive all at once (two, then
  three, each with more health per chapter), and even a fully upgraded player could be charged by two at a time. Now
  they come one at a time, the next a few seconds after one falls. Their health per chapter is ×0.85 in Chapter 2
  and ×1.0 in Chapter 3 (it was ×1.1 and ×1.5; Chapter 1 is unchanged), and in Chapters 2 and 3 the horde spawns at
  60% while a Tank is up.
- **3-1 The Docks** peaks at 1.8 zombies a second with up to 26 alive (was 2.2 and 30), and **3-4 The Ferry**'s horde
  peaks at 1.1 a second (was 1.4).
- **A bot now plays every paid level before release.** With the Chapter 1 guns and two levels of every Armory
  upgrade, it has to win each level of Chapters 2 and 3 at least once in five tries. Before these changes it could
  not win 2-4, 3-1 or 3-4.
- **Old processors.** Godot 4.5 and later need SSE4.2 on x86_64. On a processor without it (for example a 2008
  Core 2 Duo) the engine stopped before showing anything; the launcher now explains why in a notification.

## 1.0.0 (2026-11-20)

The first release, made with Godot 4.7.

- Real-time 2D lighting: your torch, street lamps, muzzle flashes, explosions and fire, with shadows from every wall,
  car and crate. Each chapter has its own night and weather: ash, rain and lightning, and fog.
- A dodge roll, grenades, hordes, kill streaks, hit-stop and slow motion on the last kill.

- Twelve levels in three chapters: Maple Street (the suburbs at dusk), Downtown (night) and The Harbor (fog).
- Five kinds of goal: survive, escape with fuel, defend a generator, clear a horde and bring down the Tank.
- Six kinds of dead: walkers, runners, brutes, spitters, bloaters and the Tank.
- Six weapons: pistol, shotgun, SMG and rifle (found in Chapter 1), and the flamethrower and crossbow (Arsenal).
- Endless mode with your longest run to beat.
- The Armory: five upgrades bought with scrap earned by playing, and the scrap can be given back to spend again.
- Five survivors to play as (Sam free; Rosa, Hank, Jules and Mo in the Survivors pack).
- Keyboard and mouse, two touch sticks, and TV remote or gamepad. Without a mouse it aims and fires for you.
- Story mode (half damage), screen shake, lightning flashes, sound and music settings.
- The store: Chapters 2 and 3, the Arsenal, the Survivors and the Complete pack, one-time purchases through Stripe.
- Update alerts from GitHub releases; Depot copies update through Depot.
