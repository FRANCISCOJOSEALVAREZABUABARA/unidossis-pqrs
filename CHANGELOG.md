# Changelog

## 1.0.0 (2026-04-22)


### Features

* Agregar Nuevo Rol desde Consola Permisos - modelo RolPersonalizado, modal premium con selector de icono/color, APIs crear/eliminar rol, migracion 0025 ([2c2162b](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/2c2162b88d66b1ccfcd08df1e8aba70429aa1290))
* consola central administracion, inventario componentes, indicadores CSAT, permisos por rol, footers version ([f4c33f3](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/f4c33f34b35b421c9be0412d10fc7660b2dc6eb8))
* **fase1:** Estabilización, pruebas automatizadas, SLA y recuperación de contraseña híbrida ([ec6d50e](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/ec6d50e7ee6e4e8ce0ef5cc37bd12e9b97254871))
* **fase2:** plantillas HTML email, paginacion APIs, README actualizado ([f036235](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/f0362355216b1efade2ca13ed36837b5a4e0e862))
* implementar CI/CD profesional y mejoras al portal cliente ([fe14738](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/fe14738b569db7e42f8713d1d9e521d6f2217066))
* panel Control de Cambios premium, timeline de commits, visor de diff, revert de cambios locales ([90cc4e3](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/90cc4e38782c5940e374b0982cc030ec99245611))
* PQRS manual, autocomplete premium, sidebar toggle, auto-crear clientes ([082b6fa](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/082b6facd2be3e6336d5f9e80f7425f9f6c15047))
* regional editable, soportes internos, pagina error 500 premium con codigos, sidebar toggle fix, GitHub Actions deploy ([f2ae8b0](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/f2ae8b0ad6414866b4c2246fd40b26540b8ad31c))
* **sla:** comando verificar_sla mejorado + template HTML alerta ([51a7830](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/51a783011501eb650ef1b160d23c68724d158729))


### Bug Fixes

* cache-busting CSS v2.1.1 para forzar recarga de estilos popover en produccion ([852e370](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/852e37040147a1ec80c868d81dd6fc6d2a5944de))
* corregir conflicto de typing_extensions en requirements para CI ([acd46b7](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/acd46b71c66990037ef565f3b4af8b3fea36e29d))
* corregir formato railway.toml ([90d9d6d](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/90d9d6d6d1d05d43add53c8e29cf1e8ed8d0438b))
* corregir overflow horizontal del layout - main-content con width/max-width calculados para sidebar fijo ([e8dca39](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/e8dca39e1f139bc35462d9d082788f38ce79bacc))
* corregir version httpx en requirements para compatibilidad con CI ([e15f6be](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/e15f6be0bfdcd9edeb7571cea4ea36cac7ba3d65))
* corregir versiones de requirements.txt para Railway Linux ([37f83c9](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/37f83c9db66b558af732c00bb9f39335151b96b1))
* corregir visibilidad del boton ViewAs en todas las paginas admin ([44936bb](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/44936bb13353b69940e65dc7635f62899f90b9e8))
* crear perfil superadmin para usuario admin en produccion ([d59ba3a](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/d59ba3a74a3494d7099ce86a31bcf0aa3edea6f4))
* Dashboard - chips de estado preservan cliente_id y q al filtrar por estado ([cafc96e](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/cafc96e34c0ef8145d80a0038849bf0d7e4e1962))
* mover settings popover fuera del sidebar para evitar overflow:hidden en produccion ([8241155](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/82411552fee06fc1c177b576956dce366976afc9))
* popover toggle con inline styles para compatibilidad cross-browser ([c61f259](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/c61f259c65a711360f62dfad42cc428b39138966))
* posicionamiento dinamico del popover - calcula posicion desde BoundingRect del boton, siempre visible en cualquier tamaño de pantalla ([d988340](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/d9883400f42096b828a09aeb5fd243228fc64779))
* simplificar deploy y crear perfil superadmin correctamente ([dd13dbb](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/dd13dbb65dc225534c9743f84a2725fa87c648da))
* simplificar deploy y crear perfil superadmin correctamente ([cd67cdb](https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/commit/cd67cdb8f1de198bb18f2fcdc4f82697e648c01b))
