// Lógica del frontend para el Dashboard de PQRS Unidossis

document.addEventListener('DOMContentLoaded', () => {
    console.log("Dashboard de PQRS Inicializado.");

    // 1. Alternar Sidebar
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.querySelector('.sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }

    // 2. Botón de Sincronización (Simulación)
    const syncBtn = document.querySelector('.btn-primary');
    if (syncBtn) {
        syncBtn.addEventListener('click', () => {
            const originalText = syncBtn.innerHTML;
            syncBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sincronizando...';
            
            setTimeout(() => {
                syncBtn.innerHTML = originalText;
                alert("Bandeja sincronizada exitosamente con Microsoft Graph (Simulación)");
            }, 2000);
        });
    }

    // 3. Panel de KPIs y SLAs
    const viewKpiBtn = document.getElementById('viewKpiBtn');
    const closeKpiBtn = document.getElementById('closeKpiBtn');
    const kpiPanel = document.getElementById('kpiPanelRight');
    const mainTable = document.getElementById('mainTableRight');

    if (viewKpiBtn && kpiPanel && mainTable) {
        viewKpiBtn.addEventListener('click', (e) => {
            e.preventDefault();
            kpiPanel.style.display = 'block';
            mainTable.style.display = 'none';
        });
    }

    if (closeKpiBtn && kpiPanel && mainTable) {
        closeKpiBtn.addEventListener('click', () => {
            kpiPanel.style.display = 'none';
            mainTable.style.display = 'block';
        });
    }

    // 4. Alertas de Configuración y Perfil
    const configBtn = document.getElementById('configBtn');
    if (configBtn) {
        configBtn.addEventListener('click', (e) => {
            e.preventDefault();
            alert("⚙ Módulo de Configuración\n\nPróximamente: Reglas de SLA, Gestión de Usuarios e Integración con Microsoft.");
        });
    }

    const userProfileBtn = document.getElementById('userProfileBtn');
    if (userProfileBtn) {
        userProfileBtn.addEventListener('click', () => {
            alert("👤 Mi Cuenta (Admin Unidossis)\n\nPerfil, Roles y Seguridad.");
        });
    }

    // 5. Búsqueda en Vivo (Simulación en index.html)
    const searchInput = document.querySelector('.search-bar input');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase();
            const rows = document.querySelectorAll('.pqrs-table tbody tr');
            
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
});

// LÓGICA DE AI CHAT COPILOT
function toggleAiChat() {
    const windowChat = document.getElementById('aiChatWindow');
    const bubble = document.getElementById('aiChatBubble');
    if (windowChat.style.display === 'none' || windowChat.style.display === '') {
        windowChat.style.display = 'flex';
        bubble.style.transform = 'scale(0) rotate(180deg)';
    } else {
        windowChat.style.display = 'none';
        bubble.style.transform = 'scale(1) rotate(0deg)';
    }
}
