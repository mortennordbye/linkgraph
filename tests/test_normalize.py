from collections import Counter

import pytest

from linkgraph import normalize as N


@pytest.mark.parametrize("a,b", [
    ("Acme", "Acme AS"), ("Acme", "ACME Norge AS"), ("Acme", " acme, inc. "),
    ("Initech", "initech"), ("Globex", "Globex Nordics"),
    ("Universitetet i Oslo", "Universitetet i Oslo (UiO)"), ("Self-employed", "Self Employed"),
    ("Smith & Co", "Smith and Co"),
])
def test_company_key_merges(a, b):
    assert N.company_key(a) == N.company_key(b)


def test_company_key_keeps_distinct_and_nonempty():
    assert N.company_key("Acme") != N.company_key("Acme Bank")
    assert N.company_key("AS") == "as"  # never strips to nothing
    assert N.company_key("Norway AS") == "norway"
    assert N.company_key("") == ""


def test_display_name_prefers_most_common():
    assert N.display_name(Counter({"Acme AS": 3, "Acme": 1})) == "Acme AS"
    assert N.display_name(Counter({"Acme AS": 1, "Acme": 1})) == "Acme"


def test_slugs():
    assert N.slug_from_url("https://www.linkedin.com/in/Ada-L/") == "ada-l"
    assert N.slug_from_url("www.linkedin.com/in/ada-l") == "ada-l"
    assert N.slug_from_url("https://www.linkedin.com/in/cora%C3%A9") == "coraé"
    assert N.slug_from_url("") == ""
    assert N.slugs_from_urls("https://www.linkedin.com/in/a,https://www.linkedin.com/in/b") == ["a", "b"]


@pytest.mark.parametrize("title,tier", [
    ("Chief Technology Officer", 4), ("CTO", 4), ("Co-Founder & CEO", 4), ("Daglig leder", 4),
    ("Partner", 4), ("VP Engineering", 3), ("Head of Product", 3), ("Direktør for salg", 3),
    ("Avdelingsleder IT", 3), ("Engineering Manager", 2), ("Tech Lead", 2), ("Senior Developer", 2),
    ("Seksjonssjef", 2), ("Software Engineer", 1), ("", 1), ("Director of Sales", 3),
])
def test_tiers(title, tier):
    assert N.seniority_tier(title) == tier


def test_generic():
    assert N.is_generic(N.company_key("Self-Employed"))
    assert not N.is_generic(N.company_key("Acme"))
