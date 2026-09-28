(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const statusEl = document.getElementById("status");
  const gridEl = document.getElementById("grid");
  const btnDelete = document.getElementById("btn-delete");
  const selected = new Set();
  const blobUrls = [];

  function authHeaders() {
    const initData = (tg && tg.initData) || "";
    return {
      Authorization: "tma " + initData,
      "X-Telegram-Init-Data": initData,
    };
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function syncDeleteButton() {
    btnDelete.disabled = selected.size === 0;
    btnDelete.textContent =
      selected.size === 0 ? "Удалить" : `Удалить (${selected.size})`;
  }

  function toggleCard(card, id) {
    if (selected.has(id)) {
      selected.delete(id);
      card.classList.remove("selected");
    } else {
      selected.add(id);
      card.classList.add("selected");
    }
    syncDeleteButton();
  }

  async function loadImageBlob(imageId) {
    const res = await fetch(`/api/images/${imageId}/file`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("file " + res.status);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    blobUrls.push(url);
    return url;
  }

  async function loadGallery() {
    setStatus("Загрузка…");
    gridEl.innerHTML = "";
    selected.clear();
    syncDeleteButton();
    blobUrls.splice(0).forEach((u) => URL.revokeObjectURL(u));

    const res = await fetch("/api/images", { headers: authHeaders() });
    if (!res.ok) {
      setStatus("Не удалось загрузить список (" + res.status + ")");
      return;
    }
    const data = await res.json();
    const images = data.images || [];
    if (!images.length) {
      setStatus("Пока нет сохранённых фото. Пришли фото боту в личку.");
      return;
    }
    setStatus(images.length + " фото — выбери и удали ненужные");

    for (const item of images) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "card";
      card.dataset.id = item.image_id;

      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      card.appendChild(img);

      const check = document.createElement("span");
      check.className = "check";
      check.textContent = "✓";
      card.appendChild(check);

      card.addEventListener("click", () => toggleCard(card, item.image_id));
      gridEl.appendChild(card);

      loadImageBlob(item.image_id)
        .then((url) => {
          img.src = url;
        })
        .catch(() => {
          img.alt = "ошибка";
        });
    }
  }

  btnDelete.addEventListener("click", async () => {
    if (!selected.size) return;
    const ids = Array.from(selected);
    const ok =
      tg && tg.showConfirm
        ? await new Promise((resolve) => {
            tg.showConfirm(
              `Удалить ${ids.length} фото? Восстановить нельзя.`,
              resolve
            );
          })
        : window.confirm(`Удалить ${ids.length} фото?`);
    if (!ok) return;

    btnDelete.disabled = true;
    setStatus("Удаляю…");
    let failed = 0;
    for (const id of ids) {
      const res = await fetch(`/api/images/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) failed += 1;
    }
    if (failed) {
      setStatus(`Удалено с ошибками: ${failed}`);
      if (tg && tg.showAlert) tg.showAlert(`Не удалось удалить: ${failed}`);
    } else if (tg && tg.HapticFeedback) {
      tg.HapticFeedback.notificationOccurred("success");
    }
    await loadGallery();
  });

  loadGallery().catch((e) => {
    console.error(e);
    setStatus("Ошибка загрузки. Открой Mini App из бота.");
  });
})();
