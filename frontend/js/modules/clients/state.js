export let activeInboundId = null;
export let activeInboundProtocol = "";
export let editModeClientEmail = null;
export let loadInboundsCallbackGlobal = null;

export function setEditModeEmail(email) {
    editModeClientEmail = email;
}

export function setLoadInboundsCallback(cb) {
    loadInboundsCallbackGlobal = cb;
}

export function setActiveInboundProtocol(proto) {
    activeInboundProtocol = proto;
}

export function setActiveInboundId(id) {
    activeInboundId = id;
}
