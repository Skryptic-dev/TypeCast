# TypeCast Assets

TypeCast can load editable PNG files from this folder. If a file is missing, the game falls back to its original code-drawn art.

Images are currently used at `1x` game scale. If the game scale is changed to `1.25x`, `1.5x`, etc., the code-drawn fallback is used so Tk does not display tiny unscaled sprites.

Use transparent PNGs for sprites. Use opaque PNGs for full scene replacements.

## Scene Backgrounds

Folder:

```text
assets/scenes/
```

Supported files:

```text
default.png
pond.png
creek.png
pier.png
garden.png
halloween.png
cute.png
abyss.png
lava.png
```

Recommended size:

```text
320x174
```

These draw behind the progress ring, rod, cat, fish, bubbles, and info panel. If the image is opaque, it fully replaces the code-drawn pond scene.

## Fish

Folder:

```text
assets/fish/
```

Fallback:

```text
assets/fish/default.png
```

By rarity:

```text
assets/fish/rarity/common.png
assets/fish/rarity/uncommon.png
assets/fish/rarity/rare.png
assets/fish/rarity/epic.png
assets/fish/rarity/legendary.png
assets/fish/rarity/secret.png
assets/fish/rarity/ultra_rare.png
```

By exact fish name:

```text
assets/fish/names/bluegill.png
assets/fish/names/voidscale_eel.png
```

Names are lowercased, spaces/punctuation become underscores.

Recommended fish sprite size:

```text
120x80
```

The sprite is centered around the hooked fish position.

## Pride / Skin Fish

Folder:

```text
assets/fish/skins/
```

Example:

```text
assets/fish/skins/trans.png
assets/fish/skins/rainbow.png
```

Skin assets are tried before name or rarity assets.

## Treasure Chest

Folder:

```text
assets/chest/
```

File:

```text
assets/chest/treasure_chest.png
```

Recommended size:

```text
90x70
```

## Blessing Visitors

Folder:

```text
assets/blessings/
```

Supported files:

```text
default.png
turtle.png
squid.png
manatee.png
eel.png
```

Recommended size:

```text
120x90
```

## Cat

Folder:

```text
assets/cat/
```

File:

```text
assets/cat/aphrodite.png
```

Recommended size:

```text
100x110
```

## Rod And Bobber

Folder:

```text
assets/rod/
```

Supported files:

```text
default.png
level_0.png
level_1.png
level_2.png
...
level_13.png
bobber.png
```

Recommended sizes:

```text
rod level image: 180x90
bobber.png: 28x28
```

Rod images draw over the existing rod art. Transparent PNGs work best.
