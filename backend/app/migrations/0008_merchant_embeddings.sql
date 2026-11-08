-- One vector per merchant key and embedding model, for chat's merchant search. Vectors
-- are unit length, stored as float32 (Python array "f"); a new model embeds everything again.
CREATE TABLE merchant_embeddings (
    merchant_key TEXT NOT NULL,
    model        TEXT NOT NULL,
    vector       BLOB NOT NULL,
    PRIMARY KEY (merchant_key, model)
);
