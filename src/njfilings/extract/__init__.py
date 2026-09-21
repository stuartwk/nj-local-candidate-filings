"""County extractors. Each reads from `cache/` and returns `model.Contest`.

No extractor touches the network — capture already did that, and a parser that
could refetch would eventually refetch instead of failing loudly.
"""
