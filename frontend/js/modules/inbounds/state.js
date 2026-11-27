export let editInboundId = null;
export let originalClients = [];

export function setEditInboundId(val) {
    editInboundId = val;
}

export function setOriginalClients(val) {
    originalClients = val;
}

export function generateRandomPassword(length = 16) {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let password = "";
    for (let i = 0; i < length; i++) {
        password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return password;
}

let _tabSwitchHandler = null;

export function registerTabSwitchHandler(fn) {
    _tabSwitchHandler = fn;
}

export function switchInboundModalTab(tabName) {
    return _tabSwitchHandler ? _tabSwitchHandler(tabName) : false;
}
