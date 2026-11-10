### Naming a molecule no longer prints RDKit's parse and kekulize notes
- The inorganic name table stored hydronium as `[H3O+]`, which RDKit rejects, so the entry was never used and the first name of a session printed a parse error. The key is now `[OH3+]`, the form RDKit writes, and the name is still oxidanium.
- The ring table's bare purine skeleton cannot kekulize. Asking for atom numbers printed that and then kept the curated locants. It still keeps them, and it no longer prints.
