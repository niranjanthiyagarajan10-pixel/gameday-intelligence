# Gameday Intelligence design direction

The dashboard must look like a premium sports broadcast product, in the family of NBA Inside the Game, Prime Vision and a modern TV graphics package. It must not look like a generic AI app.

## 1. The feel

- Black canvas, white type, team colours as the only strong colour.
- Bold condensed headlines and big numbers. The numbers are the hero.
- Dense with data, but calm. Thin rules, lots of alignment, no decoration.
- Looks like it could sit on a broadcast feed tonight.

Reference points: NBA Inside the Game shot difficulty and leverage pages, Prime Video Thursday Night Football graphics, F1 TV timing screens, Bloomberg terminal density.

## 2. Banned (the "AI slop" list)

- Blue or purple gradients, indigo primary buttons, the default Tailwind or shadcn look.
- Glassmorphism, blur panels, glows, neon outlines, animated gradient borders.
- Soft rounded cards everywhere with drop shadows. Radius is 2 to 4 px at most.
- Sparkle icons, robot icons, "AI powered" badges, emoji in the UI.
- Generic stock icons used as decoration. Icons only when they carry meaning.
- Pastel chart colours and rainbow categorical palettes.
- Centered hero layouts with big empty space. This is a dashboard, not a landing page.

## 3. Tokens

Define these as CSS variables in `web/src/styles/tokens.css`. Tailwind reads them. No raw hex in components.

```
--bg:          #000000   page
--surface:     #0B0C0E   panels
--surface-2:   #141519   raised rows, hover
--line:        #24262B   rules and grid lines
--line-dash:   #3A3D44   dashed gridlines in charts
--text:        #F4F4F1   primary text
--text-muted:  #8C9097   labels, axes
--text-dim:    #5A5E66   miss markers, disabled
--signal:      #E8FF3A   live indicator, focus ring, the one non-team accent
--up:          #38E07B   positive change
--down:        #FF4D4D   negative change
--home:        set from the home club colour
--away:        set from the away club colour
```

The default theme is dark. A light theme is not needed.

Each fictional club has a primary and secondary colour picked for contrast on black. Never two similar colours in one match. Check both against `--bg` for at least 3:1 contrast.

## 4. Type

- Display and numbers: Barlow Condensed, weights 600 to 800, uppercase for headings and team codes.
- Body and labels: Barlow, weights 400 to 600.
- All numbers use `font-variant-numeric: tabular-nums` so they do not jump while updating.
- Load from Google Fonts or self-host in `web/public/fonts`.

Scale:
```
hero number   56 / 1.0   Barlow Condensed 800    (xG total, win probability)
score         44 / 1.0   Barlow Condensed 800
section head  22 / 1.1   Barlow Condensed 700, uppercase, letter-spacing 0.02em
card title    18 / 1.2   Barlow Condensed 700
body          15 / 1.45  Barlow 400
label         12 / 1.2   Barlow 600, uppercase, letter-spacing 0.06em, --text-muted
```

## 5. Layout

- 12 column grid, 16 px gutters, max width 1600 px. Designed for 1920 x 1080 first, because that is what the video records.
- Panels sit on `--surface` with a 1 px `--line` border. No shadows.
- Section labels sit above panels, small caps style, like "MORE DIFFICULT" and "LESS DIFFICULT" in the NBA beeswarm.
- Must still work at 1280 px wide and on a phone in a single column, but do not spend demo time on mobile polish.

## 6. Charts

Use recharts or plain SVG. Rules for every chart:
- No chart borders, no background fills, no 3D, no pie charts.
- Gridlines are dashed `--line-dash`, only where they help reading.
- Axis labels in the label style. Direction hints at the ends ("MORE DIFFICULT" on the left, "LESS DIFFICULT" on the right).
- Team colour for the team's data. Grey `--text-dim` for misses and context.
- Every chart has a big headline number in the top left of its panel, like "1.84 xG" with "2 goals from 13 shots" under it.

Specific charts:
- Shot quality beeswarm: copy the NBA layout. One row per team, team crest at left, filled dot for goals, grey cross for misses, xG axis 0 to 1.
- Win probability: a stepped line with three bands (home, draw, away). Mark goals and red cards with small vertical ticks.
- Momentum: a centered bar that leans toward the team in control, filled with that team's colour.
- Leverage table: dense rows, tabular numbers, a small inline bar for total leverage, sortable headers.
- Team shape strip: a thin horizontal timeline with three shades for low block, mid block and high press.

## 7. The pitch

- Dark pitch: `#0E1A12` grass with subtle mowing stripes (white at 3 percent opacity) and `#FFFFFF` lines at 25 percent opacity. Full markings: penalty arcs, corner arcs, and goals drawn with white posts and a net. No other textures.
- Players are kit tokens: a circle in the team colour, trimmed and numbered in the club's second colour, with a soft ground shadow. Goalkeepers wear a dark kit trimmed in the team colour. A small white tick shows the direction of travel, a short streak in team colour shows a sprint, and the player on the ball gets a thin white ring.
- The ball is a classic black and white football. It spins as it travels, grows and casts an offset shadow when it is in the air, and leaves a short trail.
- Movement glides between tracking frames. A goal ripples the net; no rings or flashes on the pitch itself.
- Name tags appear on the focused player and on players involved in the current card.
- Player focus mode dims everyone else to 30 percent and draws a soft heat trail for the focused player.

## 8. Overlay cards

- Look like broadcast lower thirds, not chat bubbles.
- Left edge has a 4 px bar in the team colour. Card kind label on top ("KEY MOMENT", "SHAPE CHANGE"), then one or two lines of text, then one hero number.
- Slide in from the right over 200 ms, hold, then settle into the moments list.
- "Show evidence" and "Explain simply" are text buttons, not pill buttons.

## 9. Motion

- Numbers tick to new values over 300 ms. No bouncing.
- Respect `prefers-reduced-motion`: no slides, numbers swap instantly.
- The live dot pulses slowly in `--signal`. Nothing else pulses.

## 10. Trace panel

- Styled like a dev console: monospace (JetBrains Mono), compact rows, agent name, step, time in ms, status in `--up` or `--down`.
- This is the one place that is allowed to look technical.

## 11. Quality bar

Before each milestone demo, take a screenshot at 1920 x 1080 and check:
1. Does it look like a sports broadcast product, not an AI app?
2. Is any element on the banned list?
3. Are all numbers tabular and aligned?
4. Can you read the main number in each panel in under a second?
