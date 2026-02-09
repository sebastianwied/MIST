"""Science agent manifest definition."""

from mist_client import ManifestBuilder

MANIFEST = (
    ManifestBuilder("science")
    .description("Scientific article search and library management")
    .command("search", "Search arXiv and Semantic Scholar", args={"query": "str"})
    .command("import", "Import a paper by ID or URL", args={"identifier": "str"})
    .command("articles", "List saved articles", args={"tag": "str"})
    .command("article", "Show article details", args={"id": "int"})
    .command("tag", "Tag an article", args={"article_id": "int", "tag": "str"})
    .command("tags", "List all tags")
    .command("pdf", "Download PDF for an article", args={"article_id": "int"})
    .panel("library", "Library", "browser", default=True)
    .build()
)
