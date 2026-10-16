from sermon_worker.lectionary import choose_readings, mentions, normalise_reference, parse_insert, split_verses

INSERT = """Collect of the Day
Keep, O Lord, your household the Church.
Old Testament Reading
Isaiah 5:1-7
Let me sing for my beloved my love song concerning his vineyard. 2 He dug it and cleared it
of stones. 3And now, O inhabitants of Jerusalem, judge between me and my vineyard.
Reader: The word of the Lord.
People: Thanks be to God.
New Testament Reading
2 Corinthians 13:(5-10)11-14
(5 Examine yourselves, to see whether you are in the faith.) 11 Finally, brothers, rejoice. Aim for restora-
tion, comfort one another.
 3
Sources: The Collect of the Day is taken from the Book of Common Prayer 2019. Scripture quotations are
taken from The ESV Bible. Used by permission. All rights reserved.
12 Greet one another with a holy kiss.
Reader: The word of the Lord.
The Holy Gospel
Deacon: The Holy Gospel of Our Lord Jesus Christ, according to St. Matthew.
People: Glory to you, Lord Christ.
Matthew 21:33-35
"Hear another parable. There was a master of a house who planted 40 vines. 34 When the season
drew near, he sent his servants. 35 And the tenants beat one.
Deacon: The Gospel of the Lord.
"""


def test_parse_insert_extracts_three_readings():
    readings = parse_insert(INSERT)
    assert [(r.kind, r.reference) for r in readings] == [
        ("Old Testament", "Isaiah 5:1-7"),
        ("New Testament", "2 Corinthians 13:5-14"),
        ("Gospel", "Matthew 21:33-35"),
    ]
    isaiah = readings[0].passage.verses
    assert [n for n, _ in isaiah] == ["1", "2", "3"] and isaiah[2][1].startswith("And now")


def test_page_footer_and_hyphenation_are_cleaned():
    corinthians = " ".join(t for _, t in parse_insert(INSERT)[1].passage.verses)
    assert "Sources:" not in corinthians and "restoration" in corinthians and "kiss" in corinthians


def test_numbers_inside_verses_are_not_split():
    gospel = parse_insert(INSERT)[2].passage.verses
    assert [n for n, _ in gospel] == ["33", "34", "35"] and "40 vines" in gospel[0][1]


def test_normalise_reference():
    assert normalise_reference("2 Corinthians 13:(5-10)11-14") == "2 Corinthians 13:5-14"
    assert normalise_reference("Matthew 21:33-44") == "Matthew 21:33-44"


def test_split_verses_first_verse_unnumbered():
    assert split_verses("John 3:16-17", "For God so loved the world. 17 For God did not send") == [
        ("16", "For God so loved the world."), ("17", "For God did not send")]


def test_choose_readings_needs_evidence():
    readings = parse_insert(INSERT)
    sermon = "Turn with me to second Corinthians. In 2 Corinthians Paul says examine yourselves. Matthew once."
    assert mentions("2 Corinthians 13:5-14", sermon) == 2
    assert [r.reference for r in choose_readings(readings, sermon)] == ["2 Corinthians 13:5-14"]
    assert choose_readings(readings, "A sermon about grace with no book named.") == []
