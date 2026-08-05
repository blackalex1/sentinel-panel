import { apiFetch } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadSettings } from "./core.js";

export function setupBackupsListeners() {
    // Card 6: Backups Settings Save
    const btnSaveBackups = document.getElementById("btn-save-backups");
    if (btnSaveBackups) {
        btnSaveBackups.addEventListener("click", async () => {
            const enable = document.getElementById("setting-backup-enable").checked;
            const telegram = document.getElementById("setting-backup-telegram").checked;
            const interval = document.getElementById("setting-backup-interval").value;
            const rotationInput = document.getElementById("setting-backup-rotation");
            const rotation = rotationInput ? parseInt(rotationInput.value) : 7;
            const encrypt = document.getElementById("setting-backup-encrypt").checked;

            if (isNaN(rotation) || rotation <= 0) {
                showToast("Количество бэкапов для ротации должно быть целым положительным числом", "error");
                return;
            }

            let verifyPassword = "";
            const encryptInput = document.getElementById("setting-backup-encrypt");
            const initialEncrypt = encryptInput ? encryptInput.dataset.initial === "true" : false;
            
            if (initialEncrypt && !encrypt && window.backupPasswordSet) {
                const promptMsg = t("settings_backup_pwd_disable_prompt", "Для отключения шифрования бэкапов введите текущий пароль:");
                const pwdInput = prompt(promptMsg);
                if (pwdInput === null) {
                    if (encryptInput) encryptInput.checked = true;
                    const backupPasswordGroup = document.getElementById("setting-backup-password-group");
                    if (backupPasswordGroup) backupPasswordGroup.style.display = "block";
                    return;
                }
                if (!pwdInput.trim()) {
                    showToast(t("settings_backup_pwd_disable_required", "Для отключения шифрования необходимо ввести пароль!"), "error");
                    if (encryptInput) encryptInput.checked = true;
                    const backupPasswordGroup = document.getElementById("setting-backup-password-group");
                    if (backupPasswordGroup) backupPasswordGroup.style.display = "block";
                    return;
                }
                verifyPassword = pwdInput.trim();
            }

            btnSaveBackups.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    backup_enable: enable,
                    backup_telegram: telegram,
                    backup_interval: interval,
                    backup_rotation: rotation,
                    backup_encrypt: encrypt,
                    verify_password: verifyPassword
                })
            });
            btnSaveBackups.disabled = false;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                const checkInput = document.getElementById("setting-backup-password-check");
                if (checkInput) checkInput.value = "";
                loadSettings();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
                if (initialEncrypt && !encrypt) {
                    if (encryptInput) encryptInput.checked = true;
                    const backupPasswordGroup = document.getElementById("setting-backup-password-group");
                    if (backupPasswordGroup) backupPasswordGroup.style.display = "block";
                }
            }
        });
    }

    // Card 6: Backups Download
    const btnDownloadBackup = document.getElementById("btn-download-backup");
    if (btnDownloadBackup) {
        btnDownloadBackup.addEventListener("click", () => {
            window.location.href = "/api/system/backup/download";
        });
    }

    // Card 6: Clear all backups
    const btnClearBackups = document.getElementById("btn-clear-backups");
    if (btnClearBackups) {
        btnClearBackups.addEventListener("click", async () => {
            const confirmed = await showConfirmDialog(t("confirm_clear_backups", "Вы уверены, что хотите безвозвратно удалить все локальные резервные копии с сервера?"));
            if (!confirmed) {
                return;
            }
            
            btnClearBackups.disabled = true;
            try {
                const res = await apiFetch("/api/system/backup/clear", { method: "POST" });
                if (res && res.success) {
                    showToast(res.msg || "Локальные бэкапы успешно удалены!");
                } else {
                    showToast(res ? res.msg : "Не удалось удалить локальные бэкапы", "error");
                }
            } catch (err) {
                showToast("Ошибка при удалении бэкапов: " + err, "error");
            } finally {
                btnClearBackups.disabled = false;
            }
        });
    }

    // Card 6: Backups Upload Triggers
    const btnTriggerUpload = document.getElementById("btn-trigger-upload-backup");
    const fileInput = document.getElementById("backup-file-input");
    if (btnTriggerUpload && fileInput) {
        btnTriggerUpload.addEventListener("click", () => {
            fileInput.click();
        });

        fileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const confirmed = await showConfirmDialog(t("settings_backup_confirm_restore", "Вы уверены, что хотите восстановить базу данных? Это сотрет все текущие подключения и пользователей и перезапишет их данными из файла бэкапа!"));
            if (!confirmed) {
                fileInput.value = "";
                return;
            }

            const formData = new FormData();
            formData.append("file", file);

            btnTriggerUpload.disabled = true;
            const originalText = btnTriggerUpload.innerHTML;
            btnTriggerUpload.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Восстановление...`;

            try {
                let res = await apiFetch("/api/system/backup/upload", {
                    method: "POST",
                    body: formData
                });
                
                while (res && !res.success && (res.code === "password_required" || res.code === "invalid_password")) {
                    const promptMsg = res.code === "password_required"
                        ? t("settings_backup_pwd_prompt", "Файл бэкапа зашифрован. Введите пароль для расшифровки:")
                        : t("settings_backup_pwd_invalid_prompt", "Неверный пароль. Пожалуйста, введите корректный пароль для расшифровки:");
                    
                    const password = prompt(promptMsg);
                    if (password === null) {
                        break;
                    }
                    
                    formData.set("password", password);
                    res = await apiFetch("/api/system/backup/upload", {
                        method: "POST",
                        body: formData
                    });
                }
                
                if (res && res.success) {
                    showToast(res.msg || "База данных успешно восстановлена!");
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                } else {
                    showToast(res ? res.msg : "Не удалось восстановить бэкап", "error");
                }
            } catch (err) {
                showToast("Ошибка при загрузке бэкапа: " + err, "error");
            } finally {
                btnTriggerUpload.disabled = false;
                btnTriggerUpload.innerHTML = originalText;
                fileInput.value = "";
            }
        });
    }

    // Helper for random password generation
    function generateRandomPassword(length = 16) {
        const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+";
        let pwd = "";
        for (let i = 0; i < length; i++) {
            pwd += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return pwd;
    }

    // Backup Enable input toggle rotation visibility
    const backupEnableInput = document.getElementById("setting-backup-enable");
    if (backupEnableInput) {
        backupEnableInput.addEventListener("change", (e) => {
            const rotationGroup = document.getElementById("setting-backup-rotation-group");
            if (rotationGroup) {
                rotationGroup.style.display = e.target.checked ? "" : "none";
            }
        });
    }

    // Backup Encryption inputs visibility toggle
    const backupEncryptInput = document.getElementById("setting-backup-encrypt");
    if (backupEncryptInput) {
        backupEncryptInput.addEventListener("change", (e) => {
            const checked = e.target.checked;
            const backupPasswordGroup = document.getElementById("setting-backup-password-group");
            const initialEncrypt = backupEncryptInput.dataset.initial === "true";
            
            if (checked) {
                if (!initialEncrypt || !window.backupPasswordSet) {
                    const modal = document.getElementById("backup-pwd-setup-modal");
                    if (modal) {
                        document.getElementById("setup-backup-password").value = "";
                        document.getElementById("setup-backup-confirm").value = "";
                        modal.classList.add("active");
                    }
                    e.target.checked = false;
                    if (backupPasswordGroup) backupPasswordGroup.style.display = "none";
                } else {
                    if (backupPasswordGroup) backupPasswordGroup.style.display = "block";
                }
            } else {
                if (backupPasswordGroup) backupPasswordGroup.style.display = "none";
            }
        });
    }

    // Modal buttons for Backup Password Setup
    const modalSetup = document.getElementById("backup-pwd-setup-modal");
    if (modalSetup) {
        const btnGen = document.getElementById("btn-setup-backup-gen");
        const btnSave = document.getElementById("backup-pwd-setup-save");
        const btnCancel = document.getElementById("backup-pwd-setup-cancel");
        const btnClose = document.getElementById("backup-pwd-setup-close");
        const inputPwd = document.getElementById("setup-backup-password");
        const inputConfirm = document.getElementById("setup-backup-confirm");

        if (btnGen && inputPwd) {
            btnGen.addEventListener("click", () => {
                const generated = generateRandomPassword(16);
                inputPwd.value = generated;
                if (inputConfirm) inputConfirm.value = generated;
            });
        }

        const closeModal = () => {
            modalSetup.classList.remove("active");
            const checkbox = document.getElementById("setting-backup-encrypt");
            const initialEncrypt = checkbox ? checkbox.dataset.initial === "true" : false;
            if (!initialEncrypt) {
                if (checkbox) checkbox.checked = false;
                const backupPasswordGroup = document.getElementById("setting-backup-password-group");
                if (backupPasswordGroup) backupPasswordGroup.style.display = "none";
            }
        };

        if (btnCancel) btnCancel.addEventListener("click", closeModal);
        if (btnClose) btnClose.addEventListener("click", closeModal);

        if (btnSave && inputPwd && inputConfirm) {
            btnSave.addEventListener("click", async () => {
                const password = inputPwd.value.trim();
                const confirmPwd = inputConfirm.value.trim();

                if (!password || !confirmPwd) {
                    showToast(t("settings_backup_fields_required", "Заполните все поля для смены пароля!"), "error");
                    return;
                }
                if (password !== confirmPwd) {
                    showToast(t("settings_backup_passwords_mismatch", "Новые пароли не совпадают!"), "error");
                    return;
                }

                btnSave.disabled = true;
                try {
                    const res = await apiFetch("/api/settings/backup/password", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            current_password: "",
                            new_password: password
                        })
                    });

                    if (res && res.success) {
                        showToast(res.msg || t("settings_backup_pwd_changed", "Пароль шифрования бэкапов успешно изменен!"));
                        window.backupPasswordSet = true;
                        modalSetup.classList.remove("active");
                        
                        const checkbox = document.getElementById("setting-backup-encrypt");
                        if (checkbox) {
                            checkbox.checked = true;
                            const backupPasswordGroup = document.getElementById("setting-backup-password-group");
                            if (backupPasswordGroup) backupPasswordGroup.style.display = "block";
                            
                            const btnSaveBackups = document.getElementById("btn-save-backups");
                            if (btnSaveBackups) btnSaveBackups.click();
                        }
                    } else {
                        showToast(res ? res.msg : "Не удалось сохранить пароль", "error");
                    }
                } catch (err) {
                    showToast("Ошибка при сохранении пароля: " + err, "error");
                } finally {
                    btnSave.disabled = false;
                }
            });
        }
    }

    // Change Backup Password
    const btnChangeBackupPassword = document.getElementById("btn-change-backup-password");
    if (btnChangeBackupPassword) {
        btnChangeBackupPassword.addEventListener("click", async () => {
            const currentPassword = document.getElementById("setting-backup-current-password").value;
            const newPassword = document.getElementById("setting-backup-new-password").value;
            const confirmPassword = document.getElementById("setting-backup-confirm-password").value;

            if (!currentPassword) {
                showToast(t("settings_backup_current_password_required", "Для смены пароля введите текущий пароль!"), "error");
                return;
            }
            if (!newPassword || !confirmPassword) {
                showToast(t("settings_backup_fields_required", "Заполните все поля для смены пароля!"), "error");
                return;
            }
            if (newPassword !== confirmPassword) {
                showToast(t("settings_backup_passwords_mismatch", "Новые пароли не совпадают!"), "error");
                return;
            }

            btnChangeBackupPassword.disabled = true;
            try {
                const res = await apiFetch("/api/settings/backup/password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        current_password: currentPassword,
                        new_password: newPassword
                    })
                });

                if (res && res.success) {
                    showToast(res.msg || t("settings_backup_pwd_changed", "Пароль шифрования бэкапов успешно изменен!"));
                    document.getElementById("setting-backup-current-password").value = "";
                    document.getElementById("setting-backup-new-password").value = "";
                    document.getElementById("setting-backup-confirm-password").value = "";
                } else {
                    showToast(res ? res.msg : "Не удалось изменить пароль", "error");
                }
            } catch (err) {
                showToast("Ошибка при смене пароля: " + err, "error");
            } finally {
                btnChangeBackupPassword.disabled = false;
            }
        });
    }

    // Auto-generator button in Change Password section
    const btnChangeGen = document.getElementById("btn-change-backup-gen");
    const newPwdInput = document.getElementById("setting-backup-new-password");
    const confirmPwdInput = document.getElementById("setting-backup-confirm-password");
    if (btnChangeGen && newPwdInput) {
        btnChangeGen.addEventListener("click", () => {
            const generated = generateRandomPassword(16);
            newPwdInput.value = generated;
            if (confirmPwdInput) confirmPwdInput.value = generated;
        });
    }
}
