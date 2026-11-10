from check_squad import same_person


def test_same_person():
    assert same_person("França", "França")
    assert same_person("K. Hirose", "Kei Hirose")
    assert not same_person("K. Hirose", "Kaio Nunes")
    assert not same_person("Y. Sayuri", "Kei Sayuri")
    assert not same_person("Jorge", "Jorge Silva")
