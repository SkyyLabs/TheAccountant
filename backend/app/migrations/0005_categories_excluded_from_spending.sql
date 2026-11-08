-- Money moving between the user's own accounts is not spending: a card payment is money out
-- of the bank account and money in on the card, so counting it would count the purchases twice.
ALTER TABLE categories ADD COLUMN excluded_from_spending INTEGER NOT NULL DEFAULT 0
    CHECK (excluded_from_spending IN (0, 1));

UPDATE categories SET excluded_from_spending = 1
    WHERE is_default = 1 AND name IN ('Transfers', 'Card Payments');
