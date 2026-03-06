import datetime as dt

import pytest

from mnamer.metadata import Metadata, MetadataEpisode, MetadataMovie

pytestmark = pytest.mark.local

TEXT_CASES = ["test", "Test", "TEST", "TeSt"]


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata__convert_synopsis(value):
    metadata = Metadata(synopsis=value)
    assert metadata.synopsis == "Test"


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata__convert_container(value):
    metadata = Metadata(container=value)
    assert metadata.container == ".test"


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata__convert_group(value):
    metadata = Metadata(group=value)
    assert metadata.group == "TEST"


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata__convert_quality(value):
    metadata = Metadata(quality=value)
    assert metadata.quality == "test"


def test_metadata__format():
    with pytest.raises(NotImplementedError):
        format(Metadata())


@pytest.mark.parametrize("value", ["1987/10/01", "1987-10-01", "1987.10.01"])
def test_metadata_episode__convert__date(value):
    metadata = MetadataEpisode(date=value)
    assert metadata.date == dt.date(1987, 10, 1)


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata_episode__convert_series(value):
    metadata = MetadataEpisode(series=value)
    assert metadata.series == "Test"


def test_metadata_episode__convert_season():
    metadata = MetadataEpisode(season=1)
    assert metadata.season == 1


def test_metadata_episode__convert_episode():
    metadata = MetadataEpisode(episode=1)
    assert metadata.episode == 1


def test_metadata_episode__format_default():
    metadata = MetadataEpisode(series="Spongebob Squarepants", season=4, episode=4)
    actual = format(metadata)
    expected = "Spongebob Squarepants - 04x04"
    assert actual == expected


def test_metadata_episode__specials__00x00():
    metadata = MetadataEpisode(season=0, episode=1, series="Parks and Recreation")
    actual = format(metadata, "{series} - {season:02}x{episode:02}")
    expected = "Parks and Recreation - 00x01"
    assert actual == expected


def test_metadata_episode__specials__s00e00():
    metadata = MetadataEpisode(season=0, episode=1, series="Parks and Recreation")
    actual = format(metadata, "{series} - S{season:02}E{episode:02}")
    expected = "Parks and Recreation - S00E01"
    assert actual == expected


def test_metadata_episode__format_with_specifiers():
    metadata = MetadataEpisode(series="Spongebob Squarepants", season=4, episode=4)
    format_spec = "{series[0]}/{series} season={season} episode={episode:04}"
    actual = format(metadata, format_spec)
    expected = "S/Spongebob Squarepants season=4 episode=0004"
    assert actual == expected


@pytest.mark.parametrize("value", TEXT_CASES)
def test_metadata_movie__convert_name(value):
    metadata = MetadataMovie(name=value)
    assert metadata.name == "Test"


def test_metadata_movie__format_default():
    metadata = MetadataMovie(name="Napoleon Dynamite", year="2004")
    expected = "Napoleon Dynamite (2004)"
    actual = format(metadata)
    assert actual == expected


@pytest.mark.parametrize(
    "format_spec",
    (
        "{name} - {year} - {group}",
        "{group} - {name} - {year}",
        "{name} - {group} - {year}",
    ),
)
def test_metadata_movie__format_missing_field(format_spec: str):
    metadata = MetadataMovie(name="jojo rabbit", year="2019")
    expected = "Jojo Rabbit - 2019"
    actual = format(metadata, format_spec)
    assert actual == expected


def test_metadata_movie__format_with_specifiers():
    metadata = MetadataMovie(name="pineapple express")
    format_spec = "{name[0]}/{name}"
    expected = "P/Pineapple Express"
    actual = format(metadata, format_spec)
    assert actual == expected


# mediaid tests ----------------------------------------------------------------


def test_metadata_movie__mediaid_tmdb_takes_priority():
    metadata = MetadataMovie(id_tmdb="12345", id_imdb="tt0012345")
    assert metadata.mediaid == "tmdb-12345"


def test_metadata_movie__mediaid_imdb_fallback():
    metadata = MetadataMovie(id_imdb="tt0012345")
    assert metadata.mediaid == "imdb-tt0012345"


def test_metadata_movie__mediaid_none_when_no_ids():
    metadata = MetadataMovie(name="Some Movie", year="2020")
    assert metadata.mediaid is None


def test_metadata_movie__mediaid_in_format():
    metadata = MetadataMovie(name="Inception", year="2010", id_tmdb="27205")
    actual = format(metadata, "{name} ({year}) [{mediaid}]")
    assert actual == "Inception (2010) [tmdb-27205]"


def test_metadata_movie__mediaid_in_as_dict():
    metadata = MetadataMovie(id_tmdb="27205")
    assert metadata.as_dict()["mediaid"] == "tmdb-27205"


def test_metadata_episode__mediaid_tvdb_takes_priority():
    metadata = MetadataEpisode(id_tvdb="153021", id_tvmaze="73")
    assert metadata.mediaid == "tvdb-153021"


def test_metadata_episode__mediaid_tvmaze_fallback():
    metadata = MetadataEpisode(id_tvmaze="73")
    assert metadata.mediaid == "tvmaze-73"


def test_metadata_episode__mediaid_none_when_no_ids():
    metadata = MetadataEpisode(series="Breaking Bad", season=1, episode=1)
    assert metadata.mediaid is None


def test_metadata_episode__mediaid_in_format():
    metadata = MetadataEpisode(
        series="The Walking Dead", season=1, episode=1, id_tvdb="153021"
    )
    actual = format(metadata, "{series} - S{season:02}E{episode:02} [{mediaid}]")
    assert actual == "The Walking Dead - S01E01 [tvdb-153021]"


def test_metadata_episode__mediaid_in_as_dict():
    metadata = MetadataEpisode(id_tvdb="153021")
    assert metadata.as_dict()["mediaid"] == "tvdb-153021"
