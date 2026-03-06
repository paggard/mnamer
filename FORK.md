# mnamer — Fork Changes

This document describes the features and fixes added on top of the upstream mnamer codebase.

---

## New template tokens

### `{mediaid}`

Embeds a source-database-prefixed ID into the filename or path template.

| Media type | Priority | Example value |
|------------|----------|---------------|
| Movie | TMDb → IMDb | `tmdbid-27205`, `imdbid-tt1375666` |
| Episode | TVDb → TVmaze | `tvdbid-153021`, `tvmazeid-73` |

**Usage:**

```
# movie_format
{name}.({year}).[{mediaid}]/{name}.({year}).{extension}
# → Inception.(2010).[tmdbid-27205]/Inception.(2010).mkv

# episode_format
{series}.S{season:02}E{episode:02}.{title}.[{mediaid}].{extension}
# → Breaking.Bad.S01E01.Pilot.[tvdbid-153021].mkv
```

The token is silently omitted (brackets and all padding are cleaned up by the existing `str_fix_padding` logic) when no database ID is available.

---

### `{resolution}`, `{codec}`, `{audio_lang}` (requires ffmpeg)

When `ffmpeg_path` is set, mnamer runs `ffprobe` on each source file before renaming and populates three new tokens from the actual media streams.

**Configuration:**

```json
{
    "ffmpeg_path": "/usr/local/bin/ffmpeg"
}
```

or via CLI:

```
mnamer --ffmpeg-path /usr/local/bin/ffmpeg <files>
```

| Token | Description | Example values |
|-------|-------------|----------------|
| `{resolution}` | Width-based label | `4K`, `1440p`, `1080p`, `720p`, `576p`, `480p` |
| `{codec}` | Normalised codec name | `H265`, `H264`, `AV1`, `VP9`, `MPEG4`, … |
| `{audio_lang}` | Audio stream summary | `MULTI.` (multiple streams) or absent for single-stream files |

Resolution thresholds: ≥3840 px wide → `4K`; ≥2560 → `1440p`; ≥1920 → `1080p`; ≥1280 (height ≥ 720) → `720p`.

**Usage:**

```
# movie_format in .mnamer-v2.json
"{name}.({year}).[{mediaid}]/{name}.({year}).{audio_lang}{resolution}.{codec}.{extension}"

# Example output
Interstellar.(2014).[tmdbid-157336]/Interstellar.(2014).MULTI.1080p.H265.mkv
```

`ffprobe` is expected in the same directory as the `ffmpeg` binary. If probing fails for any reason the tokens are simply left blank.

---

## Inline per-token `.replace()` transform

Format strings now support an inline substitution directly on any single token, using the syntax:

```
{field.replace('pattern','replacement')}
```

`pattern` is treated as a regular expression. The substitution is applied to the rendered value of that token only, independently of the global `replace_after` map.

**Examples:**

```
# Replace colons in titles with a dash+space
{title.replace(':','- ')}

# Strip "The " prefix from a series name
{series.replace('^The /','')}

# Result of combining with other tokens
{name.replace('&','and')}.({year}).{extension}
# "Batman & Robin.(1997).mkv" → "Batman and Robin.(1997).mkv"
```

The `replace_after` dictionary substitutions are applied to the token value **before** the inline pattern, so word-level replacements feed into the regex correctly.

---

## `replace_after_dir` setting

Controls whether the `replace_after` substitution map is also applied to directory path components produced by the format string's directory portion.

| Value | Behaviour |
|-------|-----------|
| `true` (default) | `replace_after` runs on every directory segment as well as the filename |
| `false` | `replace_after` applies only to the filename |

**Example** – with `replace_after: {" ": "."}` and `replace_after_dir: true`:

```
movie_format: "{name} ({year})/{name} ({year}).{extension}"

# replace_after_dir: true
Interstellar (2014)/Interstellar (2014).mkv  →  Interstellar.(2014)/Interstellar.(2014).mkv

# replace_after_dir: false
Interstellar (2014)/Interstellar (2014).mkv  →  Interstellar (2014)/Interstellar.(2014).mkv
```

Set in `.mnamer-v2.json`:

```json
{
    "replace_after_dir": true
}
```

---

## Smart in-place directory rename for movies

When a movie already lives in its own subdirectory inside a library root and only the directory/file names need to change (no cross-device move), mnamer now **renames the existing directory** rather than moving individual files. This avoids a full copy+delete cycle and is significantly faster for large files.

The optimisation activates automatically when all of the following are true:

- The target is a movie.
- The format string produces a subdirectory (e.g. `{name} ({year})/…`).
- The source file's parent directory and the target directory share the same grandparent (i.e. both are exactly one level deep inside the same library root).
- The target directory does not yet exist.

No configuration is required; the behaviour is transparent to the user.

---

## Bug fixes

- **`bulk_apply` falsiness bug** — settings whose value is `False` or `0` were previously ignored when loading from a config file or CLI because `bulk_apply` used `if v` to guard `setattr`. Changed to `if v is not None` so boolean and zero-value settings are applied correctly.
- **Duplicate `language` parse** — `Target._parse()` was attempting to read `path_data["language"]` twice (once without and once with an exception guard). The duplicate call is removed; the remaining one is wrapped in the `try/except MnamerException` block.
