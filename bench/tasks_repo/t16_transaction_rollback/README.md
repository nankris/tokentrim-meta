# Transaction Rollback

Store.transaction() is a nested transaction context manager. On any BaseException leaving a block, restore the entire data dict (including nested mutable values) to its state when that block began and re-raise the same exception. Successful blocks keep changes. An inner rollback caught inside an outer transaction must preserve earlier outer changes, and an outer rollback must undo successful inner work. Keep store.data the same dict object for existing observers; nested object identities need not survive rollback.

Run `python -m unittest discover -s tests -q` from this directory.
