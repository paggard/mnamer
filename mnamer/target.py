from __future__ import annotations

import datetime as dt
import re
from os import path
from pathlib import Path
from shutil import move
from typing import Any, ClassVar

from guessit import guessit  # type: ignore

from mnamer.exceptions import MnamerException
from mnamer.language import Language
from mnamer.metadata import Metadata, MetadataEpisode, MetadataMovie
from mnamer.providers import Provider
from mnamer.setting_store import SettingStore
from mnamer.types import MediaType, ProviderType
from mnamer.utils import (
    crawl_in,
    crawl_in_dirs,
    filename_replace,
    filter_blacklist,
    filter_containers,
    is_subtitle,
    probe_media_info,
    str_replace,
    str_sanitize,
    str_scenify,
)


class Target:
    """Manages metadata state for a media file and facilitates its relocation."""

    _providers: ClassVar[dict[ProviderType, Provider]] = {}

    _settings: SettingStore
    _provider: Provider
    _has_moved: bool
    _has_renamed: bool
    _raw_metadata: dict[str, str]
    _parsed_metadata: Metadata

    source: Path
    metadata: Metadata

    def __init__(self, file_path: Path, settings: SettingStore | None = None):
        self.source = file_path
        self._settings = settings or SettingStore()
        self._has_moved = False
        self._has_renamed = False
        self._parse(file_path)
        self._probe()
        self._replace_before()
        self._parse_ids_from_filename()
        self._override_metadata_ids()
        self._register_provider()

    def __str__(self) -> str:
        if isinstance(self.source, Path):
            return str(self.source.resolve())
        else:
            return str(self.source)

    @classmethod
    def populate_paths(cls: type[Target], settings: SettingStore) -> list[Target]:
        """Creates a list of Target objects for media files found in paths."""
        file_paths = crawl_in(settings.targets, settings.recurse)
        file_paths = filter_blacklist(file_paths, settings.ignore)
        file_paths = filter_containers(file_paths, settings.mask)
        targets = [cls(file_path, settings) for file_path in file_paths]
        targets = list(dict.fromkeys(targets))  # unique values
        targets = list(filter(cls._matches_media, targets))
        return targets

    @classmethod
    def reset_providers(cls):
        cls._providers.clear()

    @staticmethod
    def _matches_media(target: Target) -> bool:
        if not target._settings.media:
            return True
        else:
            return target._settings.media is target.metadata.to_media_type()

    @property
    def provider_type(self) -> ProviderType:
        provider_type = self._settings.api_for(self.metadata.to_media_type())
        assert provider_type
        return provider_type

    @property
    def directory(self) -> Path | None:
        settings_key = f"{self.metadata.to_media_type().value}_directory"
        directory = getattr(self._settings, settings_key)
        return Path(directory) if directory else None

    @property
    def destination(self) -> Path:
        """
        The destination Path for the target based on its metadata and user
        preferences.
        """
        if self.directory:
            dir_head_ = format(self.metadata, str(self.directory))
            dir_head_ = str_sanitize(dir_head_)
            dir_head = Path(dir_head_)
        else:
            dir_head = self.source.parent
        self.metadata._replace_after = self._settings.replace_after  # type: ignore[attr-defined]
        file_path = format(self.metadata, self._settings.formatting_for(self.metadata))
        del self.metadata._replace_after  # type: ignore[attr-defined]
        dir_tail, filename = path.split(Path(file_path))
        filename = filename_replace(filename, self._settings.replace_after)
        if self._settings.scene:
            filename = str_scenify(filename)
        if self._settings.lower:
            filename = filename.lower()
        filename = str_sanitize(filename)
        if dir_tail:
            dir_parts = Path(dir_tail).parts
            processed_parts: list[str] = []
            for part in dir_parts:
                if self._settings.replace_after_dir:
                    part = filename_replace(part, self._settings.replace_after)
                if self._settings.scene:
                    part = str_scenify(part)
                if self._settings.lower:
                    part = part.lower()
                part = str_sanitize(part)
                processed_parts.append(part)
            dir_tail = str(Path(*processed_parts))
        directory = Path(dir_head, dir_tail)
        return Path(directory, filename)

    def _parse(self, file_path: Path):
        path_data: dict[str, Any] = {"language": self._settings.language}
        if is_subtitle(self.source):
            try:
                path_data["language"] = Language.parse(self.source.stem[-2:])
                file_path = Path(self.source.parent, self.source.stem[:-2])
            except MnamerException:
                pass
        options = {"type": self._settings.media, "language": path_data["language"]}
        raw_data = dict(guessit(str(file_path), options))
        if isinstance(raw_data.get("season"), list):
            raw_data = dict(guessit(str(file_path.parts[-1]), options))
        for k, v in raw_data.items():
            if hasattr(v, "alpha3"):
                try:
                    path_data[k] = Language.parse(v)
                except MnamerException:
                    continue
            elif isinstance(v, int | str | dt.date):
                path_data[k] = v
            elif isinstance(v, list) and all(isinstance(_, int | str) for _ in v):
                path_data[k] = v[0]
        if self._settings.media:
            media_type = self._settings.media
        elif path_data.get("type"):
            media_type = MediaType(path_data["type"])
        else:
            media_type = None
        # Infer media type from embedded database IDs when guessit cannot
        # determine the type on its own.
        if media_type is None:
            filename_stem = str(file_path.parts[-1])
            if re.search(r"\b(?:tmdb|imdb)id[-_]?\w+\b", filename_stem, re.IGNORECASE):
                media_type = MediaType.MOVIE
            elif re.search(r"\b(?:tvdb|tvmaze)id[-_]?\w+\b", filename_stem, re.IGNORECASE):
                media_type = MediaType.EPISODE
        meta_cls = {
            MediaType.EPISODE: MetadataEpisode,
            MediaType.MOVIE: MetadataMovie,
            None: Metadata,
        }[media_type]
        self.metadata = meta_cls()
        self.metadata.quality = (
            " ".join(
                path_data[key]
                for key in path_data
                if key
                in (
                    "audio_codec",
                    "audio_profile",
                    "screen_size",
                    "source",
                    "video_codec",
                    "video_profile",
                )
            )
            or None
        )
        try:
            self.metadata.language = path_data.get("language")
        except MnamerException:
            pass
        self.metadata.group = path_data.get("release_group")
        self.metadata.container = file_path.suffix or None
        try:
            self.metadata.language_sub = path_data.get("subtitle_language")
        except MnamerException:
            pass
        if isinstance(self.metadata, MetadataMovie):
            self.metadata.name = path_data.get("title")
            self.metadata.year = path_data.get("year")
        elif isinstance(self.metadata, MetadataEpisode):
            self.metadata.date = path_data.get("date")
            self.metadata.episode = path_data.get("episode")
            self.metadata.season = path_data.get("season")
            self.metadata.series = path_data.get("title")
            alternative_title = path_data.get("alternative_title")
            if alternative_title:
                self.metadata.series = f"{self.metadata.series} {alternative_title}"
            # adding year to title can reduce false positives
            # year = path_data.get("year")
            # if year:
            #     self.metadata.series = f"{self.metadata.series} {year}"

    def _parse_ids_from_filename(self) -> None:
        """Extracts database IDs embedded in the filename (e.g. tmdbid-518590)
        and populates the corresponding metadata ID fields.  Settings-supplied
        IDs (applied later by _override_metadata_ids) take precedence."""
        filename = self.source.stem
        id_patterns = {
            "id_imdb": r"\bimdbid[-_]?(tt\d+|\d+)\b",
            "id_tmdb": r"\btmdbid[-_]?(\d+)\b",
            "id_tvdb": r"\btvdbid[-_]?(\d+)\b",
            "id_tvmaze": r"\btvmazeid[-_]?(\d+)\b",
        }
        for attr, pattern in id_patterns.items():
            if not hasattr(self.metadata, attr):
                continue
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                setattr(self.metadata, attr, match.group(1))

    def _override_metadata_ids(self):
        id_types = {"imdb", "tmdb", "tvdb", "tvmaze"}
        for id_type in id_types:
            attr = f"id_{id_type}"
            if not hasattr(self.metadata, attr):
                continue  # ensure metadata subclass supports id type
            value = getattr(self._settings, attr, None)
            if not value:
                continue  # apply override if set in directives
            setattr(self.metadata, attr, value)

    def _register_provider(self) -> None:
        provider_type = self.provider_type
        if provider_type and provider_type not in self._providers:
            self._providers[provider_type] = Provider.provider_factory(
                provider_type, self._settings
            )
        self._provider = self._providers[provider_type]

    def _probe(self) -> None:
        """Probes the source file with ffprobe and populates resolution/codec/audio_lang."""
        if not self._settings.ffmpeg_path:
            return
        resolution, codec, audio_lang = probe_media_info(
            self.source, self._settings.ffmpeg_path
        )
        if resolution:
            self.metadata.resolution = resolution
        if codec:
            self.metadata.codec = codec
        if audio_lang:
            self.metadata.audio_lang = audio_lang

    def _replace_before(self) -> None:
        if not self._settings.replace_before:
            return
        for attr, value in vars(self.metadata).items():
            if not isinstance(value, str):
                continue
            if attr.startswith("_"):
                continue
            value = str_replace(value, self._settings.replace_before)
            setattr(self.metadata, attr, value)

    def query(self) -> list[Metadata]:
        """Queries the target's respective media provider for metadata."""
        results = self._provider.search(self.metadata)
        if not results:
            return []
        seen = set()
        response = []
        for idx, result in enumerate(results, start=1):
            if str(result) in seen:
                continue
            response.append(result)
            seen.add(str(result))
            if idx >= self._settings.hits:
                break
        return response

    def relocate(self) -> None:
        """Performs the action of renaming and/or moving a file."""
        destination_path = Path(self.destination).resolve()
        destination_dir = destination_path.parent
        source_parent = self.source.parent.resolve()

        # When the format places the movie inside a subdirectory AND the source
        # file is already in a sibling directory of that subdirectory (i.e. it
        # lives in the same movie-library root but under a different folder
        # name), rename the existing directory in-place instead of moving the
        # file across the filesystem.  Requirements:
        #   • target is a movie
        #   • a movie_directory base is set
        #   • the format produces a subdirectory (destination_dir != base dir)
        #   • the source's parent and the desired destination directory share
        #     the same grandparent (both are one level deep in the base dir)
        #   • the source parent is already different from the destination dir
        #   • the desired destination directory does not yet exist
        if (
            isinstance(self.metadata, MetadataMovie)
            and self.directory is not None
            and destination_dir != self.directory.resolve()
            and source_parent != destination_dir
            and source_parent.parent == destination_dir.parent
            and not destination_dir.exists()
        ):
            try:
                move(str(source_parent), destination_dir)
            except OSError as e:  # pragma: no cover
                raise MnamerException from e
            # After the directory rename the file sits at a new path; rename it
            # too if its name also needs to change.
            relocated_source = destination_dir / self.source.name
            if relocated_source != destination_path:
                try:
                    move(str(relocated_source), destination_path)
                except OSError as e:  # pragma: no cover
                    raise MnamerException from e
        else:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                move(str(self.source), destination_path)
            except OSError as e:  # pragma: no cover
                raise MnamerException from e


class DirectoryTarget(Target):
    """Manages metadata state for a directory and facilitates its rename."""

    @classmethod
    def populate_dirs(cls: type[Target], settings: SettingStore) -> list[Target]:
        """Creates a list of DirectoryTarget objects for dirs found in paths."""
        dir_paths = crawl_in_dirs(settings.targets)
        dir_paths = filter_blacklist(dir_paths, settings.ignore)
        if settings.dir_ignore:
            dir_paths = [
                p for p in dir_paths
                if not any(
                    re.search(pattern, p.name, re.IGNORECASE)
                    for pattern in settings.dir_ignore
                    if pattern
                )
            ]
        targets: list[Target] = [cls(dir_path, settings) for dir_path in dir_paths]
        targets = list(dict.fromkeys(targets))  # unique values
        targets = list(filter(cls._matches_media, targets))
        return targets

    def __init__(self, dir_path: Path, settings: SettingStore | None = None):
        self.source = dir_path
        self._settings = settings or SettingStore()
        self._has_moved = False
        self._has_renamed = False
        # Parse using directory name only so guessit doesn't get confused by
        # the full absolute path components.
        self._parse(Path(dir_path.name))
        # No _probe() — ffprobe is meaningless for directories.
        self._replace_before()
        self._override_metadata_ids()
        self._register_provider()

    @property
    def destination(self) -> Path:
        """The renamed directory Path based on dir format settings."""
        self.metadata._replace_after = self._settings.replace_after  # type: ignore[attr-defined]
        fmt = self._settings.dir_formatting_for(self.metadata)
        dir_name = format(self.metadata, fmt)
        del self.metadata._replace_after  # type: ignore[attr-defined]
        dir_name = filename_replace(dir_name, self._settings.replace_after)
        if self._settings.scene:
            dir_name = str_scenify(dir_name)
        if self._settings.lower:
            dir_name = dir_name.lower()
        dir_name = str_sanitize(dir_name)
        return self.source.parent / dir_name

    def rename_dir(self) -> None:
        """Renames the source directory to the computed destination name."""
        dest = Path(self.destination).resolve()
        try:
            move(str(self.source.resolve()), dest)
        except OSError as e:  # pragma: no cover
            raise MnamerException from e
