import pytest
from axes.utils import reset


@pytest.fixture(autouse=True)
def clear_axes_state(db):
    """
    Zera as tentativas do django-axes entre testes.

    Sem isso as falhas de login de um teste contaminam o próximo e o bloqueio
    aparece em lugares aleatórios da suite.
    """
    reset()
    yield
    reset()
