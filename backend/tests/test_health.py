def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # Ademas del estado, /health dice que version y que commit estan vivos, para
    # poder preguntar "¿que build corre?" sin login.
    assert "version" in data
    assert "commit" in data


def test_health_dice_el_commit_del_deploy_si_el_entorno_lo_expone(client, monkeypatch):
    monkeypatch.setenv("SOURCE_COMMIT", "35b55c98eb9fc847642793926470209fd3b9da78")

    data = client.get("/health").json()

    assert data["commit"] == "35b55c98eb9fc847642793926470209fd3b9da78"
