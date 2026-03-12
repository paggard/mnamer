# mnamer — Fork Changes

This document describes the features and fixes added on top of the upstream mnamer codebase.

to update you installed mnamer - use dev branch from this repo:

```
pipx install --force git+https://github.com/paggard/mnamer.git@dev
```
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

## ID-in-filename lookup

When a filename already contains a database ID — such as one produced by the `{mediaid}` token in a previous run — mnamer automatically extracts it and uses it for API lookup, bypassing title or year-based guessing entirely.

**Supported patterns** (case-insensitive; hyphens and underscores are interchangeable):

| Pattern | Example | Database |
|---------|---------|----------|
| `tmdbid-<id>` | `tmdbid-27205` | TMDb |
| `imdbid-<id>` | `imdbid-tt1375666` | IMDb |
| `tvdbid-<id>` | `tvdbid-153021` | TVDb |
| `tvmazeid-<id>` | `tvmazeid-73` | TVmaze |

**Example:** A file named `Inception.(2010).[tmdbid-27205].mkv` causes mnamer to extract `27205`, set `id_tmdb` on the metadata, and query TMDb by that exact ID rather than searching by title.

IDs supplied via command-line flags (`--id-tmdb`, `--id-imdb`, `--id-tvdb`, `--id-tvmaze`) always take precedence over IDs parsed from the filename.

### Media type inference from embedded IDs

When `guessit` cannot determine whether a file is a movie or an episode, mnamer uses the embedded ID prefix as a hint:

- `tmdbid-` or `imdbid-` in the filename → treated as a **Movie**
- `tvdbid-` or `tvmazeid-` in the filename → treated as an **Episode**

This ensures correct provider selection even when the filename contains too little textual information for guessit to classify the media type on its own.

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

Resolution thresholds (width-primary, height-fallback for sub-HD): ≥3840 px wide → `4K`; ≥2560 → `1440p`; ≥1920 → `1080p`; then height ≥ 720 → `720p`; ≥ 576 → `576p`; ≥ 480 → `480p`; otherwise `{height}p`.

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

## Directory rename mode (`--dir-mode`)

Instead of renaming individual media files, mnamer can operate on directories — identifying a folder as the container for a movie or TV show and renaming it according to a dedicated format string.

**Activation:**

```
mnamer --dir-mode [options] <path>...
```

When `--dir-mode` is set, mnamer scans each given path for **immediate child directories** (non-recursive) and treats each directory name as the media title to look up.

### New settings

| Setting | Flag | Default | Description |
|---------|------|---------|-------------|
| `dir_mode` | `--dir-mode` | `false` | Enable directory rename mode |
| `movie_dir_format` | `--movie-dir-format` | `{name} ({year})` | Format string for movie directories |
| `episode_dir_format` | `--episode-dir-format` | `{series}` | Format string for episode/series directories |
| `dir_ignore` | `--dir-ignore` | `[]` | Skip directories whose names match these regex patterns |

### How it works

1. `crawl_in_dirs()` returns all immediate subdirectories of the target paths.
2. The global `--ignore` patterns are applied (against the full path).
3. `--dir-ignore` patterns are applied against the **directory name only**, so a parent folder named "Collections" cannot accidentally suppress a legitimate child.
4. Each surviving directory is parsed with `guessit` (on the directory name alone) to extract media metadata.
5. The configured API provider is queried for a match.
6. If a match is found, the directory is renamed in-place according to `movie_dir_format` or `episode_dir_format`; if not, it is skipped.
7. All standard flags apply: `--batch`, `--test`, `--no-guess`, `--no-overwrite`, `--verbose`, `--scene`, `--lower`.

### `--test` mode

Like file renaming, `--dir-mode` fully supports `--test`: the resolved destination path is printed and counted as a success without touching the filesystem.

### `--dir-ignore`

Accepts one or more regular expressions (same syntax as `--ignore`) matched case-insensitively against the directory **name**:

```
mnamer --dir-mode --dir-ignore "Collection" ".*Pack.*" "^REMUX" /media/Movies/
```

Can also be set persistently in `.mnamer-v2.json`:

```json
{
    "dir_ignore": ["Collection", ".*Pack.*"]
}
```

### Example

```
/media/Movies/
  inception.2010.bluray/
  The.Dark.Knight.2008/
  Marvel Collection/        ← skipped via --dir-ignore "Collection"
  RARBG/                    ← skipped via --ignore (existing default)
```

```
mnamer --dir-mode --batch --dir-ignore "Collection" /media/Movies/

Processing Movie Directory "inception.2010.bluray"
  renaming to /media/Movies/Inception (2010)  ✓

Processing Movie Directory "The.Dark.Knight.2008"
  renaming to /media/Movies/The Dark Knight (2008)  ✓

2 out of 2 files processed successfully
```

---

## Bug fixes

- **`bulk_apply` falsiness bug** — settings whose value is `False` or `0` were previously ignored when loading from a config file or CLI because `bulk_apply` used `if v` to guard `setattr`. Changed to `if v is not None` so boolean and zero-value settings are applied correctly.
- **Duplicate `language` parse** — `Target._parse()` was attempting to read `path_data["language"]` twice (once without and once with an exception guard). The duplicate call is removed; the remaining one is wrapped in the `try/except MnamerException` block.
