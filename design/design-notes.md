# Design notes ## Feel Dark, modern, and fast. Big tap targets because I'll use it between sets with one hand. High contrast so it's readable in a bright gym. (Edit this in your own words.) ## Colors (estimates from the screenshot; refine with a color picker) - Background: near-black, about #0E0F0C - Main accent: bright lime green, about #C8F53C. Use it for the most important things only: the main button, the selected item, highlights - Cards: dark gray, one step lighter than the background - Text: white, with dimmer gray for secondary text - On lime surfaces, use black text and black buttons ## Shapes and type - Very rounded corners on cards and buttons - Pill-shaped (fully rounded) buttons and filter chips - Clean, rounded, modern sans-serif font (something like Outfit or Urbanist) - Headlines mix regular and bold weight for emphasis - Bottom navigation bar, with the active icon in a lime circle ## Screens needed (first pass) 1. Log a set: pick an exercise, enter weight and reps, big "Log Set" button. Show "Last time: 155 x 8" prominently, since it's the core feature of the app. 2. Exercise list: see my exercises and add a new one. (History is implemented with date headings, filtering, editing, and confirmed deletion. The macro tracker comes later.) ## Reference screenshots - ref-1-dark-lime.png - TAKE: dark background, lime accent, rounded cards, pill buttons, font style, bottom nav look - DON'T TAKE: the "Start Workout" flow and workout plan cards (my app has no workout sessions), the "Ask AI" bar, the PRO badge, the calories card ## Avoid - Cluttered screens, tiny buttons, too many menus - Too much lime. If everything is lime, nothing stands out.
￼


## Pump Progress
Keep the same dark/lime style and large touch targets. Use a two-column photo grid, upload preview, optional front/back/side category, sort control, and a larger photo dialog. Upload heading: "to you, 2000 years from now". Gallery heading: "from you, 2000 years ago". No captions or social features.

## Direction (v2)
Inspired by controlledinsanity.com (see ref-2): calm, spacious, earthy.
- Colors: near-black background, warm cream text and primary button,
  muted moss green only for "beat last time", haze blue-gray for
  secondary. No neon.
- Type: heavy all-caps headlines with tight spacing; small
  letter-spaced caps for labels.
- Shapes: sharp or barely rounded corners; rectangular buttons.
- Scene: landscape band in the header, fading into the background.
  Log card stays solid for readability.
- ref-1 (neon app): keep ONLY big tap targets and bottom nav layout.
  Ignore its colors.
- ref-2: TAKE the mood, palette, type, and spacing. DON'T TAKE their
  photo, logo, or copy.