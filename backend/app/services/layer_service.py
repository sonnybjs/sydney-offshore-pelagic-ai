from app.services.ocean_mock_service import mock_current_vectors, mock_fronts, mock_sst_grid


def get_sst_layer() -> dict:
    return mock_sst_grid()


def get_current_layer() -> dict:
    return mock_current_vectors()


def get_front_layer() -> dict:
    return mock_fronts()

