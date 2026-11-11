from check_squad import same_person


def test_same_person():
    assert same_person("Rendra", "Rendra")
    assert same_person("B. Santoso", "Budi Santoso")
    assert not same_person("B. Santoso", "Bima Nugroho")
    assert not same_person("Y. Sayuri", "Kei Sayuri")
    assert not same_person("Jorge", "Jorge Silva")
