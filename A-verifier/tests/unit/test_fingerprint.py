from libs.crawling.fingerprint import compute_fingerprint


def test_fingerprint_deterministic():
    fp1 = compute_fingerprint("shop_a", "SKU-001", "new")
    fp2 = compute_fingerprint("shop_a", "SKU-001", "new")
    assert fp1 == fp2


def test_fingerprint_is_stable_across_price_and_availability_changes():
    fp_before = compute_fingerprint("shop_a", "SKU-001", "new")
    fp_after_price_change = compute_fingerprint("shop_a", "SKU-001", "new")
    assert fp_before == fp_after_price_change


def test_fingerprint_differs_on_merchant():
    fp1 = compute_fingerprint("shop_a", "SKU-001", "new")
    fp2 = compute_fingerprint("shop_b", "SKU-001", "new")
    assert fp1 != fp2


def test_fingerprint_differs_on_condition():
    fp1 = compute_fingerprint("shop_a", "SKU-001", "new")
    fp2 = compute_fingerprint("shop_a", "SKU-001", "used")
    assert fp1 != fp2


def test_fingerprint_is_sha256_hex():
    fp = compute_fingerprint("x", "y", "new")
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
