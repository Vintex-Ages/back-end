# Exemplo de testes — substitua pelo seu domínio
#
# def test_create_user(client):
#     payload = {"name": "João", "email": "joao@email.com", "password": "123456"}
#     response = client.post("/api/v1/users/", json=payload)
#     assert response.status_code == 201
#     assert response.json()["name"] == "João"
#
#
# def test_list_users(client):
#     response = client.get("/api/v1/users/")
#     assert response.status_code == 200


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
