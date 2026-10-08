# Local cold PIT archive

Explicit cold storage; never loaded by imports, pytest, Scanner, daily update,
Shape research or LEAN. Large source/database files stay local and ignored.

The obsolete published Shape version `25137ad...` was moved here as one complete
snapshot, retaining its database, source manifest and uncertainty CSV. Its only
incoming database reference was its own manifest. The current `0ee4ddb...` core
and all strict/source locks remain in their original paths. Each moved file is
verified against the pre-move inventory SHA256; the relocation receipt records
original and archive paths. It is not a new research data source.

Other unique raw evidence already in `data/pit/raw` is left there as existing
explicit cold/source storage because source manifests lock those paths.
