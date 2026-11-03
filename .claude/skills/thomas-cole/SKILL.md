---
name: thomas-cole
description: Visual language for Ephemeris and other Lastelle work rendered in the manner of Thomas Cole's oil landscapes (The Course of Empire, The Oxbow). Load before designing, rendering, shading, lighting, coloring or reviewing any Ephemeris scene, background, material or UI surface.
---

# Thomas Cole — design skill

Damien chose Thomas Cole (1801–1848, founder of the Hudson River School) as the visual standard for Ephemeris. Every scene must read as an oil canvas Cole could have painted of the local system. This file states what Cole actually did, from the paintings and the scholarship on them, and translates each trait into rules for real-time rendering. A choice that cannot be traced to a rule here does not ship.

## Part 1. What Cole did

### The sky is the source

Cole wrote in his 1836 Essay on American Scenery that the sky is the soul of a landscape, the origin of all its light, shade and color, and that its moods decide how the land looks. He copied a method for painting skies from William Oram's treatise around 1825, kept notebooks of outdoor atmospheric studies (one labeled a thunderstorm after sunset), and in London in 1829–31 absorbed Constable's cloud studies and Turner's storm canvases. Constable's principle, which Cole echoed, was that the sky sets the scale and mood of the whole picture. In The Oxbow the sky carries the narrative: a swirling storm mass adapted from Turner's Hannibal crossing the Alps. In his pure cloud studies the handling is loose and quick; the lower body of a towering cloud is gray, gray-purple and gray-white, and only its crown is near-pure white. He put a strip of treetops along the bottom edge purely to give the sky scale.

### Light is narrative, set by time of day

The Course of Empire (1833–36, five canvases, New-York Historical Society) tells one place's history through light alone. The Savage State is a stormy dawn, sun rising from the sea, mist and cloud veiling the distance. The Arcadian State is fresh morning after the sky has cleared. The Consummation of Empire is noon in early autumn, and Cole described its chiaroscuro as broad: the whole canvas evenly and intensely lit, with few deep shadows, and that glare is meant to read as overripe. Destruction is late afternoon with a tempest and firelight. Desolation is dusk: a livid, fading light, the last sunset rays on a lone column, moonlight on the water, and the moonrise placed where the first canvas had its sunrise. Light in Cole is never neutral illumination. Its hour, color and spread carry the meaning.

### A permanent landmark against change

The same crag with its isolated boulder appears through the series while the viewpoint shifts, the city rises and falls, and nature returns. Critics read it as nature's permanence set against human transience.

### Composition

The Oxbow divides the canvas on a diagonal from lower right to upper left: storm and dark wilderness on one side, warm golden afternoon light on the other. A blasted tree in the lower-left corner frames the foreground (repoussoir) and states nature's violence. The painter appears tiny at his easel, so the land's scale is measured against a single figure. The Consummation builds on Turner's Dido Building Carthage: a central bay, monumental architecture on both banks, crowds and ships, a fountain in the foreground. Cole's canvases are large, deep and layered from dark framing foreground through a lit middle ground to a hazy distance.

### Paint and surface

Conservation analysis at the Metropolitan Museum of The Oxbow and The Consummation of Empire found ultramarine, vermilion, red, yellow and brown earths, lead white and carbon black, plus the newer pigments of his day: cobalt blue, chrome yellow, Prussian blue and an early zinc white. He mixed chrome yellow with Prussian blue for his bright greens and ground his own colors in linseed oil. Standard practice of the school, which Cole followed, built a monochrome underpainting in umbers and siennas, then thin translucent glazes over it so light passes through the layers and returns luminous, especially at dawn and dusk. Distance is scumbled: semi-opaque light paint dragged thinly over darker passages so far forms soften into haze. Impasto is reserved for what should feel physical, such as rock faces and the lit crests of forms. Crisp detail sits beside loosely worked passages. Shadows lean cool against warm light.

### The sublime and the beautiful together

Cole treated them as bound together: untouched vastness, storms and towering cloud (sublime) held in the same frame as calm, clear, golden passages (beautiful). Clear water matters to him because it reflects the sky perfectly.

## Part 2. Rules for Ephemeris

### Never a void

Space is never flat black. The background is a painted sky dome: a deep umber-to-bistre ground with layered, loosely brushed cloud masses (fbm noise, broken by stretched stroke noise so it reads as brushwork rather than smoke). The Sun is the light source of that sky, so cloud near the Sun's direction is lit warm gold with a white crown, and cloud away from it falls to gray-purple and cool umber. Never pure #000.

### One light, warm, with cool shadow

The Sun is the only key light. Lit faces take warm lead-white and chrome-yellow tints; shadows turn toward cool gray-purple and Prussian blue, never to black. The terminator carries a thin warm glaze band, the way Cole's dusk horizons glow. No ambient fill that flattens the form.

### Glaze, scumble, impasto in shaders

Shade bodies in layers: an umber underpainting value, then translucent color glazes multiplied over it, then lit-side impasto that breaks into short directional strokes (stretched noise along latitude or along the light direction). Apply scumble as atmospheric perspective: the farther a body is from the camera, the more a warm, semi-opaque haze from the sky color is laid over it, softening edges and value contrast. Saturn's rings are painted as translucent glazed bands with a dark gap, lit and shadowed by the same light, never as hard lines.

### Composition and scale

Default framings put a large dark mass in a lower corner as repoussoir (a planet in shadow, or the dark side of the sky) and let light open toward the opposite diagonal. Keep one permanent landmark on screen when it serves the view, normally the Sun. Scale is felt through small things against vast ones: the asteroid field reads as fine, numerous, catching light, against planets and sky.

### Time of day is mood, and it must be honest

Ephemeris has two views. Static is the system held to this moment. Planetary cycle runs the orbits at the chosen rate. Lighting mood may shift with the camera's relation to the Sun (looking toward the Sun is dawn/dusk glare and silhouette; looking away is cool, deep, moonlit), but it never invents data, events or objects. Every body on screen is a real catalogued body.

### Palette

Tokens are named after the pigments Cole used. Hex values are approximate swatches of the historical pigments, for screen use.

| Token | Pigment | Hex |
|---|---|---|
| `--lead-white` | lead white | #EEE7D7 |
| `--zinc-white` | zinc white (coolest highlight) | #F3F1EA |
| `--chrome-yellow` | chrome yellow | #E2B32E |
| `--yellow-ochre` | yellow ochre | #C9A04A |
| `--raw-sienna` | raw sienna | #B8813A |
| `--burnt-sienna` | burnt sienna | #8A4A26 |
| `--vermilion` | vermilion | #C9402A |
| `--raw-umber` | raw umber | #5E4B33 |
| `--burnt-umber` | burnt umber | #4A2E1E |
| `--bistre` | umber-black ground | #1E1610 |
| `--ultramarine` | ultramarine | #2E3F7A |
| `--cobalt` | cobalt blue | #3D5BA6 |
| `--prussian` | Prussian blue | #22344A |
| `--chrome-green` | chrome yellow + Prussian blue | #4E6B3A |
| `--carbon-black` | carbon black (sparingly, never as a fill) | #1C1915 |

Lastelle's Ember (#E08C35 family) stays the interface accent and the selection color; it sits naturally beside chrome yellow and sienna.

### Forbidden

Neon or saturated additive glow, flat vector fills, pure black backgrounds, sci-fi HUD line work, synthetic gradients with no brush breakup, hard hatching or engraving, and any placeholder, mock object or invented tag. Typography and UI chrome stay quiet so the canvas carries the page.

## Part 3. Review checklist

Before anything ships, check each frame against these questions. Does the sky read as the source of the light? Is there any pure black? Do shadows lean cool and lights warm? Can you see layering (underpainting value, glaze color, broken lit strokes) on the bodies up close? Does distance soften into warm haze? Is there a dark mass framing one corner and light opening on the opposite diagonal? Do the rings read as glazed paint? Is every object on screen real catalogued data?

## Sources

- Metropolitan Museum of Art, "Modern Pigments Found in Thomas Cole's Paintings Shed New Light on the Artist's Practice": https://www.metmuseum.org/perspectives/thomas-cole-conservation
- Metropolitan Museum of Art, "Thomas Cole and Clouds": https://www.metmuseum.org/perspectives/thomas-cole-clouds-oxbow
- Thomas Cole, Essay on American Scenery (1836): https://www.csun.edu/~ta3584/Cole.htm
- The Course of Empire (paintings): https://en.wikipedia.org/wiki/The_Course_of_Empire_(paintings)
- Thomas Cole National Historic Site, The Consummation of Empire: https://explorethomascole.org/project/the-consummation-of-empire/
- Thomas Cole, The Oxbow (art history text): https://uen.pressbooks.pub/arth2720/chapter/thomas-cole-the-oxbow/
- Glazing, scumbling and impasto summary: https://www.zenmuseum.com/finder/page/thomas-cole-painting-techniques
