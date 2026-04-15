// Lógica del frontend para el Dashboard de PQRS

document.addEventListener('DOMContentLoaded', () => {
    console.log("Dashboard de PQRS Inicializado.");

    // Botón de sincronización
    const syncBtn = document.querySelector('.btn-primary');
    if(syncBtn) {
        syncBtn.addEventListener('click', () => {
            const originalText = syncBtn.innerHTML;
            syncBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sincronizando...';
            
            // Simular carga de 2 segundos
            setTimeout(() => {
                syncBtn.innerHTML = originalText;
                alert("Bandeja sincronizada exitosamente con Microsoft Graph (Simulación)");
            }, 2000);
        });
    }
});
