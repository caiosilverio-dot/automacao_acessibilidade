(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const fields = () => $$("[data-field]");

  function coletarDados() {
    const out = {};
    fields().forEach((el) => { out[el.dataset.field] = el.value; });
    return out;
  }

  function aplicarDados(dados) {
    fields().forEach((el) => {
      const v = dados[el.dataset.field];
      if (v !== undefined && v !== null) el.value = v;
    });
  }

  // ---------------------------------------------------------
  // TOASTS
  // ---------------------------------------------------------
  function toast(msg, tipo = "info", ms = 4200) {
    const box = document.createElement("div");
    box.className = `toast ${tipo}`;
    box.textContent = msg;
    $("#toastContainer").appendChild(box);
    setTimeout(() => box.remove(), ms);
  }

  // ---------------------------------------------------------
  // LOADING OVERLAY
  // ---------------------------------------------------------
  const overlay = $("#loadingOverlay");
  const loadingText = $("#loadingText");
  function mostrarCarregando(msg) {
    loadingText.textContent = msg;
    overlay.classList.remove("hidden");
    $("#btnCancel").disabled = false;
  }
  function esconderCarregando() {
    overlay.classList.add("hidden");
    $("#btnCancel").disabled = true;
  }

  // ---------------------------------------------------------
  // TABS
  // ---------------------------------------------------------
  $$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab-btn").forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      $$(".tab-panel").forEach((p) => p.classList.remove("active"));
      $(`#tab-${btn.dataset.tab}`).classList.add("active");
    });
  });

  // ---------------------------------------------------------
  // STATUS DA IA (OLLAMA)
  // ---------------------------------------------------------
  async function verificarOllama() {
    const pill = $("#ollamaStatus");
    try {
      const r = await fetch("/api/status");
      const j = await r.json();
      if (j.ok) {
        pill.className = "status-pill status-ok";
        pill.innerHTML = `<span class="dot"></span> IA online — modelo "${j.modelo}"`;
      } else {
        pill.className = "status-pill status-bad";
        pill.innerHTML = `<span class="dot"></span> IA offline (usando fallback)`;
      }
    } catch {
      pill.className = "status-pill status-bad";
      pill.innerHTML = `<span class="dot"></span> IA indisponível`;
    }
  }

  // ---------------------------------------------------------
  // BANDEIRAS (AO VIVO)
  // ---------------------------------------------------------
  function pintarBandeiras(b) {
    Object.entries(b).forEach(([chave, valor]) => {
      const ok = valor === "verde";
      $$(`[data-flag="${chave}"]`).forEach((el) => {
        el.classList.toggle("flag-ok", ok);
        el.classList.toggle("flag-bad", !ok);
      });
    });
  }

  let bandeiraTimer = null;
  function agendarAtualizacaoBandeiras() {
    clearTimeout(bandeiraTimer);
    bandeiraTimer = setTimeout(atualizarBandeiras, 320);
  }

  async function atualizarBandeiras() {
    const d = coletarDados();
    try {
      const r = await fetch("/api/bandeiras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d),
      });
      const b = await r.json();
      pintarBandeiras(b);
    } catch {
      /* silencioso: indicador ao vivo não é crítico */
    }
  }

  $$(".live-flag").forEach((el) => el.addEventListener("input", agendarAtualizacaoBandeiras));

  // ---------------------------------------------------------
  // AUTOSAVE
  // ---------------------------------------------------------
  let autosaveSegundos = 30;
  async function carregarConfig() {
    try {
      const r = await fetch("/api/config");
      const j = await r.json();
      autosaveSegundos = j.autosave_segundos || 30;
    } catch { /* usa padrão */ }
  }

  async function restaurarAutosave() {
    try {
      const r = await fetch("/api/autosave");
      const j = await r.json();
      if (j && Object.keys(j).length) {
        aplicarDados(j);
        atualizarBandeiras();
      }
    } catch { /* nada salvo ainda */ }
  }

  async function salvarAutosave() {
    try {
      await fetch("/api/autosave", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coletarDados()),
      });
    } catch { /* silencioso */ }
  }

  // ---------------------------------------------------------
  // PDF
  // ---------------------------------------------------------
  $("#pdfInput").addEventListener("change", async (e) => {
    const arquivo = e.target.files[0];
    if (!arquivo) return;
    const label = $("#pdfLabel");
    label.textContent = "Lendo PDF…";
    label.className = "pdf-label";
    const fd = new FormData();
    fd.append("arquivo", arquivo);
    try {
      const r = await fetch("/api/pdf", { method: "POST", body: fd });
      const j = await r.json();
      if (j.ok) {
        $('[data-field="msg_pdf"]').value = j.mensagem;
        label.textContent = `✅ ${j.dia}`;
        label.className = "pdf-label ok";
        toast(`PDF carregado: ${j.dia}`, "ok");
      } else {
        label.textContent = "❌ Erro na leitura";
        label.className = "pdf-label err";
        toast(j.erro || "Falha ao ler o PDF.", "err");
      }
    } catch {
      label.textContent = "❌ Erro na leitura";
      label.className = "pdf-label err";
      toast("Falha ao enviar o PDF.", "err");
    }
  });

  // ---------------------------------------------------------
  // OTIMIZAR
  // ---------------------------------------------------------
  const CAMPOS_OTIMIZAVEIS = ["msg_pdf", "desc_ocorrencia", "item_d1", "item_ftt", "item_mves", "desc_5s", "msg_lideranca"];

  $("#btnOtim").addEventListener("click", async () => {
    const btn = $("#btnOtim");
    btn.disabled = true;
    mostrarCarregando("Otimizando campos via IA…");
    const campos = {};
    const dados = coletarDados();
    CAMPOS_OTIMIZAVEIS.forEach((k) => { campos[k] = dados[k] || ""; });
    try {
      const r = await fetch("/api/otimizar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campos }),
      });
      const j = await r.json();
      Object.entries(j.otimizados || {}).forEach(([chave, texto]) => {
        const el = document.querySelector(`[data-field="${chave}"]`);
        if (el && texto) el.value = texto.trim();
      });
      toast(j.mensagem || "Otimização concluída", j.otimizados && Object.keys(j.otimizados).length ? "ok" : "info");
    } catch {
      toast("Falha ao otimizar via IA.", "err");
    } finally {
      btn.disabled = false;
      esconderCarregando();
    }
  });

  // ---------------------------------------------------------
  // PREVIEW
  // ---------------------------------------------------------
  $("#btnPrev").addEventListener("click", async () => {
    const btn = $("#btnPrev");
    btn.disabled = true;
    mostrarCarregando("Gerando narração via IA…");
    atualizarBandeiras();
    try {
      const r = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coletarDados()),
      });
      const j = await r.json();
      if (j.ok) {
        $("#preview").value = j.texto;
        if (j.bandeiras) pintarBandeiras(j.bandeiras);
        toast("Preview gerado", "ok");
      } else {
        toast(j.erro || "Erro ao gerar preview.", "err");
      }
    } catch {
      toast("Falha de comunicação ao gerar preview.", "err");
    } finally {
      btn.disabled = false;
      esconderCarregando();
    }
  });

  // ---------------------------------------------------------
  // SALVAR
  // ---------------------------------------------------------
  $("#btnSave").addEventListener("click", async () => {
    const texto = $("#preview").value.trim();
    if (texto.length < 20) {
      toast("O preview está vazio. Gere o preview antes de salvar.", "err");
      return;
    }
    const btn = $("#btnSave");
    btn.disabled = true;
    mostrarCarregando("Salvando…");
    try {
      const r = await fetch("/api/salvar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
      });
      const j = await r.json();
      if (j.ok) {
        toast("DDS salvo! O boneco de Libras vai abrir em uma nova aba.", "ok", 6000);
        salvarAutosave();
      } else {
        toast(j.erro || "Erro ao salvar.", "err");
      }
    } catch {
      toast("Falha de comunicação ao salvar.", "err");
    } finally {
      btn.disabled = false;
      esconderCarregando();
    }
  });

  // ---------------------------------------------------------
  // CANCELAR
  // ---------------------------------------------------------
  $("#btnCancel").addEventListener("click", async () => {
    try { await fetch("/api/cancelar", { method: "POST" }); } catch { /* noop */ }
    toast("Cancelando…", "info");
  });

  // ---------------------------------------------------------
  // ATALHOS DE TECLADO
  // ---------------------------------------------------------
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); $("#btnOtim").click(); }
    if (e.ctrlKey && e.key.toLowerCase() === "p") { e.preventDefault(); $("#btnPrev").click(); }
    if (e.ctrlKey && e.key.toLowerCase() === "s") { e.preventDefault(); $("#btnSave").click(); }
    if (e.key === "Escape" && !$("#btnCancel").disabled) { $("#btnCancel").click(); }
  });

  // ---------------------------------------------------------
  // TRADUTOR DE VOZ
  // ---------------------------------------------------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let reconhecimento = null;
  let ouvindoVoz = false;

  function statusVoz(msg) { $("#statusVoz").textContent = msg; }

  if (!SR) {
    $("#vozAviso").classList.remove("hidden");
    $("#btnGravar").disabled = true;
  } else {
    reconhecimento = new SR();
    reconhecimento.lang = "pt-BR";
    reconhecimento.continuous = true;
    reconhecimento.interimResults = false;

    reconhecimento.onresult = (e) => {
      let novo = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) novo += e.results[i][0].transcript + " ";
      }
      novo = novo.trim();
      if (novo) {
        const area = $("#txtVoz");
        area.value = area.value ? `${area.value} ${novo}` : novo;
        statusVoz("🎤 Ouvindo… (texto atualizado)");
      }
    };
    reconhecimento.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      statusVoz(`❌ Erro no reconhecimento: ${e.error}`);
    };
    reconhecimento.onend = () => {
      if (ouvindoVoz) {
        try { reconhecimento.start(); } catch { /* já iniciado */ }
      }
    };
  }

  $("#btnGravar").addEventListener("click", () => {
    if (!reconhecimento || ouvindoVoz) return;
    try {
      reconhecimento.start();
      ouvindoVoz = true;
      $("#btnGravar").disabled = true;
      $("#btnParar").disabled = false;
      statusVoz("🎤 Ouvindo… peça para a pessoa falar perto do microfone.");
    } catch {
      statusVoz("❌ Não foi possível acessar o microfone.");
    }
  });

  $("#btnParar").addEventListener("click", () => {
    if (!reconhecimento || !ouvindoVoz) return;
    ouvindoVoz = false;
    reconhecimento.stop();
    $("#btnGravar").disabled = false;
    $("#btnParar").disabled = true;
    statusVoz("⏹️ Gravação parada.");
  });

  $("#btnLimparVoz").addEventListener("click", () => {
    $("#txtVoz").value = "";
    statusVoz("Texto limpo. Pronto para gravar.");
  });

  $("#btnApresentarVoz").addEventListener("click", async () => {
    const texto = $("#txtVoz").value.trim();
    if (texto.length < 3) {
      toast("Ainda não há texto transcrito para apresentar.", "err");
      return;
    }
    if (ouvindoVoz) $("#btnParar").click();
    mostrarCarregando("Abrindo o boneco de Libras…");
    try {
      const r = await fetch("/api/apresentar_voz", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
      });
      const j = await r.json();
      if (j.ok) {
        toast("Abrindo o boneco em uma nova aba…", "ok");
      } else {
        toast(j.erro || "Erro ao apresentar.", "err");
      }
    } catch {
      toast("Falha de comunicação ao apresentar.", "err");
    } finally {
      esconderCarregando();
    }
  });

  // ---------------------------------------------------------
  // INICIALIZAÇÃO
  // ---------------------------------------------------------
  (async function iniciar() {
    verificarOllama();
    await carregarConfig();
    await restaurarAutosave();
    atualizarBandeiras();
    setInterval(salvarAutosave, autosaveSegundos * 1000);
    window.addEventListener("beforeunload", salvarAutosave);
  })();
})();
