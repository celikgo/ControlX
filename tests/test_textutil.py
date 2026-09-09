from controlx.core.textutil import contains_signal, excerpt, heading_set, normalize, split_sections


def test_normalize_strips_markdown_noise():
    assert (
        normalize("A **Tenant**  is the\n`billing` boundary") == "a tenant is the billing boundary"
    )


def test_contains_signal_is_literal_not_fuzzy():
    text = "GraphQL first is the house style"
    assert contains_signal(text, "GraphQL first")
    # scattered tokens must NOT count - a false 'sufficient' is the expensive mistake
    assert not contains_signal(text, "GraphQL is not used")


def test_contains_signal_ignores_case_and_emphasis():
    assert contains_signal("The client **refreshes on 401**, never on a timer.", "refreshes on 401")


def test_split_sections_and_headings():
    markdown = "## One\n\nbody one\n\n## Two\n\nbody two\n"
    sections = split_sections(markdown, source="instructions.md")
    assert [s.heading for s in sections] == ["One", "Two"]
    assert sections[0].source == "instructions.md#One"
    assert heading_set(markdown) == {"one", "two"}


def test_excerpt_truncates():
    assert excerpt("x" * 500, 50).endswith("…")
