import tkinter as tk
from tkinter import messagebox
import random
import json
import os
import time

# =========================
# CONSTANTES GENERALES
# =========================
TAM_CELDA = 32
ANCHO_MAPA = 20  # columnas
ALTO_MAPA = 15  # filas

# Códigos de terreno
CAMINO = 0
MURO = 1
LIANA = 2
TUNEL = 3

# Modos de juego
MODO_ESCAPA = "ESCAPA"
MODO_CAZADOR = "CAZADOR"

# Dificultades
DIFICULTADES = {"Fácil": 1.0, "Normal": 1.5, "Difícil": 2.0}

# Tiempos (en segundos)
COOLDOWN_TRAMPA = 5
RESPAWN_ENEMIGO = 10

# Archivo de puntajes
ARCHIVO_SCORES = "scores.json"


# =========================
# CLASES DE TERRENO
# =========================


class CasillaBase:
    def __init__(self, codigo):
        self.codigo = codigo

    def puede_pasar_jugador(self):
        return False

    def puede_pasar_enemigo(self):
        return False

    def color(self):
        return "black"


class Camino(CasillaBase):
    def __init__(self):
        super().__init__(CAMINO)

    def puede_pasar_jugador(self):
        return True

    def puede_pasar_enemigo(self):
        return True

    def color(self):
        return "#d4d4d4"


class Muro(CasillaBase):
    def __init__(self):
        super().__init__(MURO)

    def color(self):
        return "#222222"


class Liana(CasillaBase):
    def __init__(self):
        super().__init__(LIANA)

    def puede_pasar_enemigo(self):
        return True

    def color(self):
        return "#228B22"  # verde


class Tunel(CasillaBase):
    def __init__(self):
        super().__init__(TUNEL)

    def puede_pasar_jugador(self):
        return True

    def color(self):
        return "#4b0082"  # morado


# =========================
# MAPA DEL JUEGO
# =========================


class GameMap:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.matriz = [[Muro() for _ in range(cols)] for _ in range(rows)]
        self.inicio = (1, 1)
        self.salida = (cols - 2, rows - 2)

    def generar(self):
        """Genera un mapa aleatorio garantizando un camino de CAMINO."""
        # 1. Inicialmente todo muros
        self.matriz = [[Muro() for _ in range(self.cols)] for _ in range(self.rows)]

        # 2. Carvar un camino aleatorio desde inicio hasta salida (solo camino normal)
        x, y = self.inicio
        sx, sy = self.salida

        self.matriz[y][x] = Camino()
        while (x, y) != (sx, sy):
            dx = sx - x
            dy = sy - y
            opciones = []
            if dx > 0:
                opciones.append((1, 0))
            if dx < 0:
                opciones.append((-1, 0))
            if dy > 0:
                opciones.append((0, 1))
            if dy < 0:
                opciones.append((0, -1))
            if not opciones:
                break
            mx, my = random.choice(opciones)
            nx, ny = x + mx, y + my
            if 0 < nx < self.cols - 1 and 0 < ny < self.rows - 1:
                x, y = nx, ny
                self.matriz[y][x] = Camino()

        # 3. Rellenar el resto con tipos aleatorios
        for j in range(1, self.rows - 1):
            for i in range(1, self.cols - 1):
                if (i, j) == self.inicio or (i, j) == self.salida:
                    self.matriz[j][i] = Camino()
                    continue
                if isinstance(self.matriz[j][i], Camino):
                    # ya es camino del recorrido principal
                    continue
                r = random.random()
                if r < 0.55:
                    self.matriz[j][i] = Camino()
                elif r < 0.7:
                    self.matriz[j][i] = Muro()
                elif r < 0.85:
                    self.matriz[j][i] = Liana()
                else:
                    self.matriz[j][i] = Tunel()

        # Asegurar inicio y salida como camino
        ix, iy = self.inicio
        sx, sy = self.salida
        self.matriz[iy][ix] = Camino()
        self.matriz[sy][sx] = Camino()

    def casilla(self, x, y):
        if 0 <= x < self.cols and 0 <= y < self.rows:
            return self.matriz[y][x]
        return Muro()  # fuera del mapa se considera muro

    def es_salida(self, x, y):
        return (x, y) == self.salida


# =========================
# ENTIDADES
# =========================


class Jugador:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.energia_max = 100
        self.energia = self.energia_max
        self.ultima_recuperacion = time.time()

    def mover(self, dx, dy, game_map, correr=False):
        pasos = 2 if correr and self.energia >= 10 else 1
        for _ in range(pasos):
            nx = self.x + dx
            ny = self.y + dy
            cas = game_map.casilla(nx, ny)
            if cas.puede_pasar_jugador():
                self.x = nx
                self.y = ny
            else:
                break
        if correr and pasos == 2:
            self.energia = max(0, self.energia - 10)

    def actualizar_energia(self):
        ahora = time.time()
        # recupera 1 punto por segundo
        if ahora - self.ultima_recuperacion >= 1.0:
            self.energia = min(self.energia_max, self.energia + 1)
            self.ultima_recuperacion = ahora


class Enemigo:
    def __init__(self, x, y, velocidad=1.0):
        self.x = x
        self.y = y
        self.vivo = True
        self.tiempo_muerte = None
        self.velocidad = velocidad  # factor de dificultad
        self.ultimo_movimiento = time.time()

    def listo_para_moverse(self):
        # enemigos más rápidos se mueven más seguido
        intervalo = max(0.2, 0.6 / self.velocidad)
        return time.time() - self.ultimo_movimiento >= intervalo

    def mover(self, jugador, game_map, modo):
        if not self.vivo:
            return
        if not self.listo_para_moverse():
            return
        self.ultimo_movimiento = time.time()

        # Direcciones posibles
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        mejor_dx, mejor_dy = 0, 0

        def distancia(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        mejor_dist = None
        for dx, dy in dirs:
            nx = self.x + dx
            ny = self.y + dy
            cas = game_map.casilla(nx, ny)
            if not cas.puede_pasar_enemigo():
                continue
            d = distancia((nx, ny), (jugador.x, jugador.y))
            if modo == MODO_ESCAPA:
                # perseguir -> minimizar distancia
                if mejor_dist is None or d < mejor_dist:
                    mejor_dist = d
                    mejor_dx, mejor_dy = dx, dy
            else:
                # huir -> maximizar distancia
                if mejor_dist is None or d > mejor_dist:
                    mejor_dist = d
                    mejor_dx, mejor_dy = dx, dy

        self.x += mejor_dx
        self.y += mejor_dy


class Trampa:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.colocada_en = time.time()


# =========================
# GESTOR DE PUNTAJES
# =========================


class ScoreManager:
    def __init__(self, archivo):
        self.archivo = archivo
        self.data = {MODO_ESCAPA: [], MODO_CAZADOR: []}
        self.cargar()

    def cargar(self):
        if os.path.exists(self.archivo):
            try:
                with open(self.archivo, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {MODO_ESCAPA: [], MODO_CAZADOR: []}

    def guardar(self):
        with open(self.archivo, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def agregar_puntaje(self, modo, nombre, puntaje):
        lista = self.data.get(modo, [])
        lista.append({"nombre": nombre, "puntaje": puntaje})
        lista.sort(key=lambda x: x["puntaje"], reverse=True)
        self.data[modo] = lista[:5]
        self.guardar()

    def obtener_top5(self, modo):
        return self.data.get(modo, [])


# =========================
# APLICACIÓN PRINCIPAL
# =========================


class GameApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Proyecto Cazadores - Escapa / Cazador")

        self.modo_actual = None
        self.dificultad = "Normal"
        self.factor_dificultad = DIFICULTADES[self.dificultad]

        self.game_map = GameMap(ANCHO_MAPA, ALTO_MAPA)
        self.jugador = None
        self.enemigos = []
        self.trampas = []
        self.ultimo_trampa = 0

        self.jugador_nombre = ""
        self.score_manager = ScoreManager(ARCHIVO_SCORES)

        self.tiempo_inicio = None
        self.puntaje = 0
        self.enemigos_atrapados = 0
        self.enemigos_escapados = 0

        self.running = False

        self.crear_ui()
        self.mostrar_ventana_registro()

    # ---------- UI ----------

    def crear_ui(self):
        top_frame = tk.Frame(self.root, bg="#111111")
        top_frame.pack(side=tk.TOP, fill=tk.X)

        self.lbl_info = tk.Label(top_frame, text="Modo: -", fg="white", bg="#111111")
        self.lbl_info.pack(side=tk.LEFT, padx=10)

        self.lbl_tiempo = tk.Label(
            top_frame, text="Tiempo: 0", fg="white", bg="#111111"
        )
        self.lbl_tiempo.pack(side=tk.LEFT, padx=10)

        self.lbl_puntaje = tk.Label(
            top_frame, text="Puntaje: 0", fg="white", bg="#111111"
        )
        self.lbl_puntaje.pack(side=tk.LEFT, padx=10)

        self.lbl_energia = tk.Label(
            top_frame, text="Energía:", fg="white", bg="#111111"
        )
        self.lbl_energia.pack(side=tk.LEFT, padx=10)

        self.canvas_energia = tk.Canvas(
            top_frame, width=120, height=16, bg="#333333", highlightthickness=0
        )
        self.canvas_energia.pack(side=tk.LEFT, padx=5)

        # Top 5 panel
        self.lbl_top_escape = tk.Label(
            top_frame, text="Top Escapa: -", fg="white", bg="#111111"
        )
        self.lbl_top_escape.pack(side=tk.RIGHT, padx=10)
        self.lbl_top_cazador = tk.Label(
            top_frame, text="Top Cazador: -", fg="white", bg="#111111"
        )
        self.lbl_top_cazador.pack(side=tk.RIGHT, padx=10)

        # Canvas principal
        self.canvas = tk.Canvas(
            self.root,
            width=ANCHO_MAPA * TAM_CELDA,
            height=ALTO_MAPA * TAM_CELDA,
            bg="black",
        )
        self.canvas.pack()

        # Bindings de teclado
        self.root.bind("<Up>", lambda e: self.mover_jugador(0, -1, False))
        self.root.bind("<Down>", lambda e: self.mover_jugador(0, 1, False))
        self.root.bind("<Left>", lambda e: self.mover_jugador(-1, 0, False))
        self.root.bind("<Right>", lambda e: self.mover_jugador(1, 0, False))

        # Correr con WASD
        self.root.bind("w", lambda e: self.mover_jugador(0, -1, True))
        self.root.bind("s", lambda e: self.mover_jugador(0, 1, True))
        self.root.bind("a", lambda e: self.mover_jugador(-1, 0, True))
        self.root.bind("d", lambda e: self.mover_jugador(1, 0, True))

        # Colocar trampa
        self.root.bind("<space>", lambda e: self.colocar_trampa())

    def mostrar_ventana_registro(self):
        self.win_reg = tk.Toplevel(self.root)
        self.win_reg.title("Registro de jugador")
        self.win_reg.grab_set()
        tk.Label(self.win_reg, text="Nombre del jugador:").pack(padx=10, pady=5)
        self.entry_nombre = tk.Entry(self.win_reg)
        self.entry_nombre.pack(padx=10, pady=5)

        tk.Label(self.win_reg, text="Dificultad:").pack(padx=10, pady=5)
        self.var_dif = tk.StringVar(value="Normal")
        tk.OptionMenu(self.win_reg, self.var_dif, *DIFICULTADES.keys()).pack(
            padx=10, pady=5
        )

        tk.Label(self.win_reg, text="Elige modo:").pack(padx=10, pady=5)

        btn_escapa = tk.Button(
            self.win_reg,
            text="Modo ESCAPA",
            command=lambda: self.iniciar_desde_registro(MODO_ESCAPA),
        )
        btn_escapa.pack(padx=10, pady=5)

        btn_cazador = tk.Button(
            self.win_reg,
            text="Modo CAZADOR",
            command=lambda: self.iniciar_desde_registro(MODO_CAZADOR),
        )
        btn_cazador.pack(padx=10, pady=5)

    def iniciar_desde_registro(self, modo):
        nombre = self.entry_nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Atención", "Debe ingresar un nombre.")
            return
        self.jugador_nombre = nombre
        self.dificultad = self.var_dif.get()
        self.factor_dificultad = DIFICULTADES[self.dificultad]
        self.win_reg.destroy()
        self.iniciar_partida(modo)

    # ---------- LÓGICA DEL JUEGO ----------

    def iniciar_partida(self, modo):
        self.modo_actual = modo
        self.lbl_info.config(
            text=f"Modo: {modo} | Jugador: {self.jugador_nombre} | Dif: {self.dificultad}"
        )

        # Generar mapa nuevo
        self.game_map.generar()

        # Crear jugador en inicio
        ix, iy = self.game_map.inicio
        self.jugador = Jugador(ix, iy)

        # Crear enemigos
        self.enemigos = []
        num_enemigos = (
            3
            if self.dificultad == "Fácil"
            else (4 if self.dificultad == "Normal" else 5)
        )
        for _ in range(num_enemigos):
            ex, ey = self.generar_posicion_enemigo()
            self.enemigos.append(Enemigo(ex, ey, velocidad=self.factor_dificultad))

        self.trampas = []
        self.ultimo_trampa = 0

        self.tiempo_inicio = time.time()
        self.puntaje = 0
        self.enemigos_atrapados = 0
        self.enemigos_escapados = 0
        self.running = True

        self.actualizar_top5_labels()
        self.loop_juego()

    def generar_posicion_enemigo(self):
        while True:
            x = random.randint(1, self.game_map.cols - 2)
            y = random.randint(1, self.game_map.rows - 2)
            if (x, y) != self.game_map.inicio and (x, y) != self.game_map.salida:
                cas = self.game_map.casilla(x, y)
                if cas.puede_pasar_enemigo():
                    return x, y

    def mover_jugador(self, dx, dy, correr):
        if not self.running:
            return
        self.jugador.mover(dx, dy, self.game_map, correr)
        # Si llega a salida en modo escapa -> gana
        if self.modo_actual == MODO_ESCAPA and self.game_map.es_salida(
            self.jugador.x, self.jugador.y
        ):
            self.fin_partida(victoria=True, motivo="¡Escapaste a tiempo!")
        self.dibujar()

    def colocar_trampa(self):
        if not self.running:
            return
        if self.modo_actual != MODO_ESCAPA:
            return
        ahora = time.time()
        # máximo 3 trampas y cooldown
        if len(self.trampas) >= 3:
            return
        if ahora - self.ultimo_trampa < COOLDOWN_TRAMPA:
            return
        # Trampa en posición del jugador
        self.trampas.append(Trampa(self.jugador.x, self.jugador.y))
        self.ultimo_trampa = ahora
        self.dibujar()

    def loop_juego(self):
        if not self.running:
            return

        # actualizar tiempo y energía
        tiempo = int(time.time() - self.tiempo_inicio)
        self.lbl_tiempo.config(text=f"Tiempo: {tiempo}s")
        self.jugador.actualizar_energia()
        self.actualizar_barra_energia()

        # mover enemigos
        for enemigo in self.enemigos:
            if not enemigo.vivo:
                # revisar respawn
                if (
                    enemigo.tiempo_muerte
                    and time.time() - enemigo.tiempo_muerte >= RESPAWN_ENEMIGO
                ):
                    ex, ey = self.generar_posicion_enemigo()
                    enemigo.x = ex
                    enemigo.y = ey
                    enemigo.vivo = True
                    enemigo.tiempo_muerte = None
                continue
            enemigo.mover(self.jugador, self.game_map, self.modo_actual)

            # comprobar colisiones según modo
            if self.modo_actual == MODO_ESCAPA:
                # si enemigo toca al jugador -> pierde
                if enemigo.x == self.jugador.x and enemigo.y == self.jugador.y:
                    self.fin_partida(victoria=False, motivo="Un cazador te atrapó.")
                    return
            else:
                # modo cazador: si jugador toca enemigo -> lo atrapa
                if enemigo.x == self.jugador.x and enemigo.y == self.jugador.y:
                    self.enemigos_atrapados += 1
                    # puntos positivos
                    self.puntaje += int(100 * self.factor_dificultad * 2)
                    enemigo.vivo = False
                    enemigo.tiempo_muerte = time.time()

            # enemigos pueden escapar por la salida en modo cazador
            if self.modo_actual == MODO_CAZADOR and self.game_map.es_salida(
                enemigo.x, enemigo.y
            ):
                self.enemigos_escapados += 1
                self.puntaje -= int(50 * self.factor_dificultad)
                enemigo.vivo = False
                enemigo.tiempo_muerte = time.time()

        # trampas en modo escapa
        if self.modo_actual == MODO_ESCAPA:
            for enemigo in self.enemigos:
                if enemigo.vivo:
                    for trampa in list(self.trampas):
                        if enemigo.x == trampa.x and enemigo.y == trampa.y:
                            # enemigo muere, trampa desaparece
                            enemigo.vivo = False
                            enemigo.tiempo_muerte = time.time()
                            self.trampas.remove(trampa)
                            # bono pequeño
                            self.puntaje += int(30 * self.factor_dificultad)

        # actualizar puntaje en función del tiempo (modo escapa)
        if self.modo_actual == MODO_ESCAPA:
            base = max(0, 1000 - tiempo * 10)
            self.puntaje = (
                int(base * self.factor_dificultad) + self.enemigos_atrapados * 30
            )
        # en modo cazador ya se actualiza en los eventos

        self.lbl_puntaje.config(text=f"Puntaje: {self.puntaje}")
        self.dibujar()

        self.root.after(100, self.loop_juego)

    def fin_partida(self, victoria, motivo):
        self.running = False
        tiempo_total = int(time.time() - self.tiempo_inicio)

        if self.modo_actual == MODO_CAZADOR:
            # Ajuste final de puntaje por tiempo: bonus pequeño
            self.puntaje += int(max(0, 500 - tiempo_total * 5) * self.factor_dificultad)

        self.lbl_puntaje.config(text=f"Puntaje: {self.puntaje}")
        self.score_manager.agregar_puntaje(
            self.modo_actual, self.jugador_nombre, self.puntaje
        )
        self.actualizar_top5_labels()

        texto = f"{motivo}\n\nPuntaje final: {self.puntaje}\nTiempo: {tiempo_total}s"
        if not victoria and self.modo_actual == MODO_ESCAPA:
            titulo = "Has perdido"
        elif not victoria:
            titulo = "Has perdido"
        else:
            titulo = "¡Has ganado!"

        if messagebox.askyesno(titulo, texto + "\n\n¿Jugar de nuevo?"):
            self.mostrar_ventana_registro()
        else:
            self.root.destroy()

    # ---------- DIBUJO ----------

    def dibujar(self):
        self.canvas.delete("all")
        # terreno
        for y in range(self.game_map.rows):
            for x in range(self.game_map.cols):
                cas = self.game_map.casilla(x, y)
                color = cas.color()
                self.canvas.create_rectangle(
                    x * TAM_CELDA,
                    y * TAM_CELDA,
                    (x + 1) * TAM_CELDA,
                    (y + 1) * TAM_CELDA,
                    fill=color,
                    outline="#555555",
                )

        # salida
        sx, sy = self.game_map.salida
        self.canvas.create_rectangle(
            sx * TAM_CELDA + 4,
            sy * TAM_CELDA + 4,
            (sx + 1) * TAM_CELDA - 4,
            (sy + 1) * TAM_CELDA - 4,
            outline="gold",
            width=3,
        )

        # trampas
        for trampa in self.trampas:
            self.canvas.create_oval(
                trampa.x * TAM_CELDA + 8,
                trampa.y * TAM_CELDA + 8,
                (trampa.x + 1) * TAM_CELDA - 8,
                (trampa.y + 1) * TAM_CELDA - 8,
                fill="red",
                outline="yellow",
            )

        # enemigos
        for enemigo in self.enemigos:
            if not enemigo.vivo:
                continue
            self.canvas.create_rectangle(
                enemigo.x * TAM_CELDA + 6,
                enemigo.y * TAM_CELDA + 6,
                (enemigo.x + 1) * TAM_CELDA - 6,
                (enemigo.y + 1) * TAM_CELDA - 6,
                fill="#ff5555",
                outline="black",
            )

        # jugador
        if self.jugador:
            self.canvas.create_oval(
                self.jugador.x * TAM_CELDA + 4,
                self.jugador.y * TAM_CELDA + 4,
                (self.jugador.x + 1) * TAM_CELDA - 4,
                (self.jugador.y + 1) * TAM_CELDA - 4,
                fill="#1e90ff",
                outline="black",
                width=2,
            )

    def actualizar_barra_energia(self):
        self.canvas_energia.delete("all")
        porc = self.jugador.energia / self.jugador.energia_max
        largo = int(120 * porc)
        color = "#00ff00" if porc > 0.5 else ("#ffff00" if porc > 0.2 else "#ff0000")
        self.canvas_energia.create_rectangle(0, 0, 120, 16, fill="#333333", outline="")
        self.canvas_energia.create_rectangle(0, 0, largo, 16, fill=color, outline="")

    def actualizar_top5_labels(self):
        top_escape = self.score_manager.obtener_top5(MODO_ESCAPA)
        top_cazador = self.score_manager.obtener_top5(MODO_CAZADOR)

        def formatear(lista):
            if not lista:
                return "-"
            return ", ".join(
                [f'{i+1}) {p["nombre"]}({p["puntaje"]})' for i, p in enumerate(lista)]
            )

        self.lbl_top_escape.config(text="Top Escapa: " + formatear(top_escape))
        self.lbl_top_cazador.config(text="Top Cazador: " + formatear(top_cazador))


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    root = tk.Tk()
    app = GameApp(root)
    root.mainloop()
