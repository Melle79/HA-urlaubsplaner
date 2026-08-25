/* Urlaubsplaner-Card – Lovelace Custom Card für das Urlaubsplaner Add-on
 *
 * Minimale Konfiguration:
 *   type: custom:urlaubsplaner-card
 *
 * Urlaube können direkt in der Karte angelegt, bearbeitet und gelöscht werden.
 * Die Karte sendet dazu Commands per `mqtt.publish` an das Add-on
 * (Topic `urlaubsplaner/cmd`); die Daten kommen aus den Entitäten
 * binary_sensor.urlaub_heute / binary_sensor.urlaub_morgen / sensor.naechster_urlaub.
 */
const CARD_VERSION = "1.0.8";
console.info(`%c URLAUBSPLANER-CARD %c v${CARD_VERSION} `,
  "color:#06281a;background:#4cc38a;font-weight:700", "color:#4cc38a;background:#1f2630");

const DEFAULTS = {
  title: "Urlaub",
  show_badges: true,
  show_next: true,
  show_strip: true,
  strip_days: 14,
  show_list: true,
  allow_edit: true,
};

function fmtTime(t) { return t ? ` · ${t} Uhr` : ""; }
function fmtDate(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || "–";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function statusOf(u) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const s = new Date(u.start + "T00:00:00"), e = new Date(u.end + "T00:00:00");
  if (e < today) return ["vorbei", "Vorbei"];
  if (s <= today) return ["aktiv", "Aktiv"];
  return ["geplant", "Geplant"];
}

class UrlaubsplanerCard extends HTMLElement {
  setConfig(config) {
    this._config = { ...DEFAULTS, ...config };
    this._editId = null;
    this._formOpen = false;
  }

  getCardSize() { return 4; }

  static getStubConfig() { return { ...DEFAULTS }; }

  set hass(hass) {
    this._hass = hass;
    const heute  = hass.states["binary_sensor.urlaub_heute"];
    const morgen  = hass.states["binary_sensor.urlaub_morgen"];
    const vorbei  = hass.states["binary_sensor.urlaub_gerade_vorbei"];
    const next = hass.states["sensor.naechster_urlaub"];
    const sig = JSON.stringify([
      heute && heute.state, morgen && morgen.state, vorbei && vorbei.state,
      next && next.state, next && next.attributes.urlaube,
      this._formOpen, this._editId,
    ]);
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(heute, morgen, vorbei, next);
  }

  _cmd(payload) {
    this._hass.callService("mqtt", "publish", {
      topic: "urlaubsplaner/cmd",
      payload: JSON.stringify(payload),
    });
  }

  _render(heute, morgen, vorbei, next) {
    const c = this._config;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    if (!next) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">
        Entitäten des Urlaubsplaner Add-ons nicht gefunden
        (<code>sensor.naechster_urlaub</code>). Läuft das Add-on?
      </div></ha-card>`;
      return;
    }

    const urlaube = Array.isArray(next.attributes.urlaube) ? next.attributes.urlaube : [];
    const vorschau = Array.isArray(next.attributes.vorschau) ? next.attributes.vorschau : [];
    const editing = this._editId ? urlaube.find((u) => u.id === this._editId) : null;

    // Badges: bevorzugt aus den binary_sensors, sonst Fallback auf das vorschau-Attribut
    const dayOn = (ent, idx) => {
      if (ent) return ent.state === "on";
      return !!(vorschau[idx] && vorschau[idx].urlaub);
    };
    const badge = (on, label, ended=false) => `<div class="badge ${on ? "on" : ended ? "ended" : ""}">
        <span class="b-label">${label}</span><span class="b-state">${on ? "Urlaub" : "—"}</span>
      </div>`;

    let nextHtml = "";
    if (c.show_next) {
      const a = next.attributes;
      if (a.beginn) {
        const when = a.aktuell_urlaub
          ? `läuft noch bis ${fmtDate(a.ende)}${fmtTime(a.endzeit)}`
          : `${fmtDate(a.beginn)}${fmtTime(a.startzeit)} – ${fmtDate(a.ende)}${fmtTime(a.endzeit)} · in ${a.in_tagen} Tagen`;
        nextHtml = `<div class="next ${a.aktuell_urlaub ? "running" : ""}">
          <ha-icon icon="mdi:airplane-takeoff"></ha-icon>
          <div><div class="n-label">${a.bezeichnung || "Urlaub"}</div>
          <div class="n-when">${when} · ${a.dauer_tage} Tage</div></div>
        </div>`;
      } else {
        nextHtml = `<div class="next muted"><ha-icon icon="mdi:airplane-takeoff"></ha-icon>
          <div class="n-when">Kein Urlaub geplant</div></div>`;
      }
    }

    let stripHtml = "";
    if (c.show_strip && vorschau.length) {
      const days = vorschau.slice(0, Math.max(7, Math.min(31, c.strip_days)));
      stripHtml = `<div class="strip">` + days.map((d, i) => `
        <div class="day ${d.urlaub ? "urlaub" : d.wochenende ? "we" : ""} ${i === 0 ? "today" : ""}"
             title="${fmtDate(d.datum)}${d.urlaub ? " – Urlaub" : ""}">
          <span class="wd">${d.wochentag}</span><span class="dn">${d.datum.slice(8)}</span>
        </div>`).join("") + `</div>`;
    }

    let listHtml = "";
    if (c.show_list) {
      const rows = urlaube.map((u) => {
        const [cls, txt] = statusOf(u);
        const actions = c.allow_edit ? `
          <button class="iconbtn" data-edit="${u.id}" title="Bearbeiten"><ha-icon icon="mdi:pencil"></ha-icon></button>
          <button class="iconbtn danger" data-del="${u.id}" title="Löschen"><ha-icon icon="mdi:delete-outline"></ha-icon></button>` : "";
        return `<div class="row">
          <span class="pill ${cls}">${txt}</span>
          <div class="r-info"><div class="r-label">${u.label || "Urlaub"}</div>
          <div class="r-range">${fmtDate(u.start)}${fmtTime(u.start_time)} – ${fmtDate(u.end)}${fmtTime(u.end_time)}</div></div>
          <div class="r-actions">${actions}</div>
        </div>`;
      }).join("");
      listHtml = `<div class="list">${rows || '<div class="empty">Noch keine Urlaube eingetragen.</div>'}</div>`;
    }

    let formHtml = "";
    if (c.allow_edit) {
      if (this._formOpen || editing) {
        formHtml = `<div class="form">
          <div class="f-title">${editing ? "Urlaub bearbeiten" : "Urlaub anlegen"}</div>
          <input type="text" id="f-label" placeholder="Bezeichnung (optional)" maxlength="60"
                 value="${editing ? (editing.label || "").replace(/"/g, "&quot;") : ""}">
          <div class="f-dates">
            <label>Von <input type="date" id="f-start" value="${editing ? editing.start : ""}"></label>
            <label class="f-time">Abfahrt <input type="time" id="f-start-time" value="${editing ? (editing.start_time||"") : ""}"></label>
            <label>Bis <input type="date" id="f-end" value="${editing ? editing.end : ""}"></label>
            <label class="f-time">Ankunft <input type="time" id="f-end-time" value="${editing ? (editing.end_time||"") : ""}"></label>
          </div>
          <div class="f-msg" id="f-msg"></div>
          <div class="f-actions">
            <button class="btn ghost" id="f-cancel">Abbrechen</button>
            <button class="btn" id="f-save">Speichern</button>
          </div>
        </div>`;
      } else {
        formHtml = `<div class="addwrap"><button class="btn ghost" id="f-open">
          <ha-icon icon="mdi:plus"></ha-icon>Urlaub eintragen</button></div>`;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        *{box-sizing:border-box}
        ha-card{padding:16px}
        .btn{border:none;border-radius:8px;padding:9px 16px;font:inherit;font-size:.9rem;font-weight:600;
             cursor:pointer;background:var(--primary-color);color:var(--text-primary-color,#fff);
             display:inline-flex;align-items:center;gap:6px}
        .btn:hover{filter:brightness(1.08)}
        .btn.ghost{background:transparent;color:var(--primary-color);border:1px solid var(--primary-color);font-weight:500}
        .btn.ghost:hover{background:rgba(127,127,127,.08);filter:none}
        .iconbtn{border:none;background:transparent;cursor:pointer;padding:6px;border-radius:50%;
                 color:var(--secondary-text-color);display:inline-flex;align-items:center}
        .iconbtn:hover{background:rgba(127,127,127,.12);color:var(--primary-text-color)}
        .iconbtn.danger:hover{color:var(--error-color)}
        .title{font-size:1.05rem;font-weight:500;margin-bottom:12px;display:flex;align-items:center;gap:8px}
        .badges{display:flex;gap:10px;margin-bottom:12px}
        .badge{flex:1;border-radius:10px;padding:8px 12px;background:var(--secondary-background-color);
               display:flex;flex-direction:column;gap:2px}
        .badge.on{background:rgba(76,195,138,.18)}
        .badge.ended{background:rgba(232,162,61,.18)}
        .badge.ended .b-state{color:#c8891a}
        .b-label{font-size:.75rem;color:var(--secondary-text-color)}
        .b-state{font-weight:600}
        .badge.on .b-state{color:#2e9e6b}
        .next{display:flex;align-items:center;gap:10px;margin-bottom:12px;
              border-radius:10px;padding:10px 12px;background:var(--secondary-background-color)}
        .next.running{background:rgba(76,195,138,.18)}
        .next ha-icon{color:var(--primary-color)}
        .n-label{font-weight:600}
        .n-when{font-size:.85rem;color:var(--secondary-text-color)}
        .next.muted .n-when{color:var(--secondary-text-color)}
        .strip{display:flex;gap:3px;margin-bottom:12px}
        .day{flex:1;text-align:center;border-radius:6px;padding:4px 0;font-size:.7rem;
             background:var(--secondary-background-color);color:var(--secondary-text-color)}
        .day.we{opacity:.55}
        .day.urlaub{background:rgba(76,195,138,.3);color:var(--primary-text-color)}
        .day.today{outline:2px solid var(--primary-color)}
        .day .wd{display:block}
        .day .dn{display:block;font-weight:600}
        .list{display:flex;flex-direction:column;gap:8px;margin-bottom:8px}
        .row{display:flex;align-items:center;gap:10px}
        .pill{font-size:.65rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
              padding:3px 8px;border-radius:999px;flex:none}
        .pill.aktiv{background:rgba(76,195,138,.2);color:#2e9e6b}
        .pill.geplant{background:rgba(122,162,255,.2);color:#5b82e6}
        .pill.vorbei{background:var(--secondary-background-color);color:var(--secondary-text-color)}
        .r-info{flex:1;min-width:0}
        .r-label{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .r-range{font-size:.82rem;color:var(--secondary-text-color)}
        .r-actions{display:flex;flex:none}
        .empty{color:var(--secondary-text-color);font-size:.88rem}
        .addwrap{margin-top:4px}
        .form{border:1px solid var(--divider-color);border-radius:10px;padding:12px;margin-top:8px;
              display:flex;flex-direction:column;gap:10px}
        .f-title{font-weight:600;font-size:.92rem}
        .form input,.form select{background:var(--secondary-background-color);border:1px solid var(--divider-color);
              border-radius:8px;color:var(--primary-text-color);padding:8px 10px;font:inherit;font-size:.9rem;width:100%;
              color-scheme:dark}
        .form input[type=time]{color-scheme:dark}
        .f-dates{display:flex;flex-wrap:wrap;gap:10px}
        .f-dates label{flex:1;min-width:120px;display:flex;flex-direction:column;gap:4px;
              font-size:.78rem;color:var(--secondary-text-color)}
        .f-dates label.f-time{flex:0 1 130px}
        .f-msg{font-size:.82rem;color:var(--error-color);min-height:1em}
        .f-actions{display:flex;gap:8px;justify-content:flex-end}
      </style>
      <ha-card>
        ${c.title ? `<div class="title"><ha-icon icon="mdi:beach"></ha-icon>${c.title}</div>` : ""}
        ${c.show_badges ? `<div class="badges">${badge(dayOn(heute, 0), "Heute")}${badge(dayOn(morgen, 1), "Morgen")}${badge(false, "Gerade vorbei", vorbei && vorbei.state === "on")}</div>` : ""}
        ${nextHtml}${stripHtml}${listHtml}${formHtml}
      </ha-card>`;

    const $ = (sel) => this.shadowRoot.querySelector(sel);

    const open = $("#f-open");
    if (open) open.addEventListener("click", () => { this._formOpen = true; this._sig = null; this.hass = this._hass; });

    const cancel = $("#f-cancel");
    if (cancel) cancel.addEventListener("click", () => {
      this._formOpen = false; this._editId = null; this._sig = null; this.hass = this._hass;
    });

    const triggerSel = $("#f-trigger");
      const actionSel = $("#f-action");
      const ACTION_LABELS = {
        heute:  {ein:"Im Urlaub EIN, sonst AUS",          aus:"Im Urlaub AUS, sonst EIN"},
        morgen: {ein:"Am Vortag EIN, sonst AUS",           aus:"Am Vortag AUS, sonst EIN"},
        vorbei: {ein:"Direkt nach Urlaub EIN, sonst AUS",  aus:"Direkt nach Urlaub AUS, sonst EIN"},
      };
      const updateActionLabels = () => {
        if (!triggerSel || !actionSel) return;
        const labels = ACTION_LABELS[triggerSel.value] || ACTION_LABELS.heute;
        actionSel.querySelector('[value=ein]').textContent = labels.ein;
        actionSel.querySelector('[value=aus]').textContent = labels.aus;
      };
      if (triggerSel) { triggerSel.addEventListener("change", updateActionLabels); updateActionLabels(); }
      const startInput = $("#f-start");
    if (startInput) startInput.addEventListener("change", () => {
      const end = $("#f-end");
      end.min = startInput.value;
      if (!end.value || end.value < startInput.value) end.value = startInput.value;
    });

    const save = $("#f-save");
    if (save) save.addEventListener("click", () => {
      const start = $("#f-start").value, end = $("#f-end").value;
      const label = $("#f-label").value.trim();
      const start_time = $("#f-start-time") ? $("#f-start-time").value : "";
      const end_time = $("#f-end-time") ? $("#f-end-time").value : "";
      if (!start || !end) { $("#f-msg").textContent = "Bitte Von- und Bis-Datum angeben."; return; }
      if (end < start) { $("#f-msg").textContent = "Das Ende darf nicht vor dem Beginn liegen."; return; }
      if (this._editId) this._cmd({ action: "update", id: this._editId, start, start_time, end, end_time, label });
      else this._cmd({ action: "add", start, start_time, end, end_time, label });
      this._formOpen = false; this._editId = null; this._sig = null;
      this.hass = this._hass;
    });

    this.shadowRoot.querySelectorAll("[data-edit]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._editId = btn.getAttribute("data-edit"); this._formOpen = true;
        this._sig = null; this.hass = this._hass;
      }));
    this.shadowRoot.querySelectorAll("[data-del]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const u = urlaube.find((x) => x.id === btn.getAttribute("data-del"));
        if (!u) return;
        if (!confirm(`„${u.label || "Urlaub"}" (${fmtDate(u.start)} – ${fmtDate(u.end)}) wirklich löschen?`)) return;
        this._cmd({ action: "delete", id: u.id });
      }));
  }

  static getConfigElement() {
    return document.createElement("urlaubsplaner-card-editor");
  }
}

class UrlaubsplanerCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...DEFAULTS, ...config }; this._render(); }
  set hass(hass) { this._hass = hass; }

  _render() {
    const c = this._config;
    const fields = [
      ["show_badges", "Badges „Heute / Morgen Urlaub“ anzeigen"],
      ["show_next", "Nächsten Urlaub anzeigen"],
      ["show_strip", "14-Tage-Streifen anzeigen"],
      ["show_list", "Urlaubsliste anzeigen"],
      ["allow_edit", "Eintragen / Bearbeiten / Löschen in der Karte erlauben"],
    ];
    this.innerHTML = `
      <style>
        .ed{display:flex;flex-direction:column;gap:10px;padding:8px 0}
        .ed label{display:flex;align-items:center;gap:10px;font-size:.92rem}
        .ed input[type=text]{flex:1;padding:8px;border:1px solid var(--divider-color);
          border-radius:8px;background:var(--secondary-background-color);color:var(--primary-text-color)}
      </style>
      <div class="ed">
        <label>Titel <input type="text" id="e-title" value="${(c.title || "").replace(/"/g, "&quot;")}"></label>
        ${fields.map(([k, l]) => `<label><input type="checkbox" id="e-${k}" ${c[k] ? "checked" : ""}> ${l}</label>`).join("")}
      </div>`;
    this.querySelector("#e-title").addEventListener("change", (ev) => this._set("title", ev.target.value));
    fields.forEach(([k]) =>
      this.querySelector(`#e-${k}`).addEventListener("change", (ev) => this._set(k, ev.target.checked)));
  }

  _set(key, value) {
    this._config = { ...this._config, [key]: value };
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: this._config }, bubbles: true, composed: true,
    }));
  }
}

customElements.define("urlaubsplaner-card", UrlaubsplanerCard);
customElements.define("urlaubsplaner-card-editor", UrlaubsplanerCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "urlaubsplaner-card",
  name: "Urlaubsplaner Card",
  description: "Urlaube anzeigen, eintragen, bearbeiten und löschen (Urlaubsplaner Add-on)",
  preview: true,
});
