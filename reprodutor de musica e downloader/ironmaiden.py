import os
import sys
import random
import threading
from urllib.parse import quote_plus
from urllib.request import urlopen
import yt_dlp
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QTimer, QPoint, QEvent, QUrl, QSize
from PyQt6.QtGui import QFileSystemModel, QPixmap, QColor, QIcon, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeView,
    QInputDialog,
    QLabel,
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QListWidget,
    QListWidgetItem,
    QSlider,
)

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass


class ItemSugestao(QFrame):
    clicado = pyqtSignal(dict)

    def __init__(self, dados):
        super().__init__()
        self.dados = dados
        self.setObjectName("cardSugestao")
        self.setFixedHeight(68)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 10, 6)
        layout.setSpacing(12)

        self.imagem_thumb = QLabel()
        self.imagem_thumb.setFixedSize(100, 56)
        self.imagem_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imagem_thumb.setObjectName("thumbSugestao")
        self.imagem_thumb.setText("...")

        layout_textos = QVBoxLayout()
        layout_textos.setContentsMargins(0, 2, 0, 2)
        layout_textos.setSpacing(4)

        self.texto_titulo = QLabel(dados.get("titulo", "Sem título"))
        self.texto_titulo.setObjectName("tituloSugestao")

        self.texto_detalhe = QLabel(dados.get("detalhe", ""))
        self.texto_detalhe.setObjectName("detalheSugestao")

        layout_textos.addWidget(self.texto_titulo)
        layout_textos.addWidget(self.texto_detalhe)
        layout_textos.addStretch()

        layout.addWidget(self.imagem_thumb)
        layout.addLayout(layout_textos, stretch=1)

    def definir_thumbnail(self, dados_imagem):
        pixmap = QPixmap()
        if pixmap.loadFromData(dados_imagem):
            pixmap_ajustado = pixmap.scaled(
                100,
                56,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.imagem_thumb.setPixmap(pixmap_ajustado)

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.dados)
        super().mousePressEvent(evento)


class JanelaPrincipal(QWidget):
    sinal_status = pyqtSignal(str)
    sinal_concluido = pyqtSignal(bool)
    sinal_resultados = pyqtSignal(int, list)
    sinal_thumbnail = pyqtSignal(int, int, bytes)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador de Músicas")
        self.resize(980, 650)

        usuario = os.path.expanduser("~")
        if os.path.isdir(os.path.join(usuario, "Músicas")):
            self.pasta_raiz = os.path.join(usuario, "Músicas")
        elif os.path.isdir(os.path.join(usuario, "Música")):
            self.pasta_raiz = os.path.join(usuario, "Música")
        elif os.path.isdir(os.path.join(usuario, "Music")):
            self.pasta_raiz = os.path.join(usuario, "Music")
        else:
            self.pasta_raiz = os.path.join(usuario, "Músicas")
            os.makedirs(self.pasta_raiz, exist_ok=True)

        os.environ["PATH"] = self.pasta_raiz + os.pathsep + os.environ.get("PATH", "")

        self.pasta_destino = self.pasta_raiz
        self.modo_filtro = "video"
        self.link_escolhido = None
        self.ignorar_alteracao_texto = False
        self.contador_busca = 0
        self.cards_sugestao = []
        self.caminho_hover = None

        self.musica_atual = None
        self.historico_tocadas = []
        self.proximas_musicas = []
        self.adicionadas_manualmente = set()
        self.modo_aleatorio = False
        self.modo_repetir = "desligado"
        self.arrastando_tempo = False

        self.tocador = QMediaPlayer(self)
        self.saida_audio = QAudioOutput(self)
        self.tocador.setAudioOutput(self.saida_audio)
        self.saida_audio.setVolume(0.85)

        self.temporizador_busca = QTimer(self)
        self.temporizador_busca.setSingleShot(True)
        self.temporizador_busca.timeout.connect(self.disparar_busca_relacionados)

        self.montar_interface()
        self.montar_botoes_hover()
        self.montar_painel_fila_flutuante()
        self.montar_popup_volume()
        self.montar_aba_sugestoes()
        self.aplicar_estilo()
        self.atualizar_botoes_filtro()
        self.atualizar_visual_controles_player()

        self.sinal_status.connect(self.atualizar_status)
        self.sinal_concluido.connect(self.finalizar_download)
        self.sinal_resultados.connect(self.preencher_sugestoes)
        self.sinal_thumbnail.connect(self.aplicar_thumbnail)

        self.tocador.mediaStatusChanged.connect(self.ao_mudar_status_midia)
        self.tocador.playbackStateChanged.connect(self.ao_mudar_estado_reproducao)
        self.tocador.positionChanged.connect(self.ao_mudar_posicao)
        self.tocador.durationChanged.connect(self.ao_mudar_duracao)
        self.tocador.metaDataChanged.connect(self.ao_atualizar_metadados)

        QApplication.instance().installEventFilter(self)

    def carregar_icone(self, nomes_arquivos):
        base_exe = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        pastas_possiveis = [
            os.path.join(base_exe, "__Código"),
            os.path.join(base_exe, "__Codigo"),
            os.path.join(self.pasta_raiz, "__Código"),
            os.path.join(self.pasta_raiz, "__Codigo"),
        ]
        for pasta in pastas_possiveis:
            for nome in nomes_arquivos:
                caminho = os.path.join(pasta, nome)
                if os.path.isfile(caminho):
                    return QIcon(caminho)
        return QIcon()

    def montar_interface(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(35, 35, 35, 28)
        layout_principal.setSpacing(12)

        self.barra_pesquisa = QLineEdit()
        self.barra_pesquisa.setPlaceholderText("Cole o link do YouTube ou digite o nome da música...")
        self.barra_pesquisa.setFixedHeight(48)
        self.barra_pesquisa.textChanged.connect(self.ao_digitar_pesquisa)
        self.barra_pesquisa.returnPressed.connect(self.iniciar_download)
        layout_principal.addWidget(self.barra_pesquisa)

        layout_controles = QHBoxLayout()
        layout_controles.setSpacing(12)

        self.botao_video = QPushButton("Apenas Vídeos")
        self.botao_video.setFixedSize(165, 42)
        self.botao_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_video.clicked.connect(self.selecionar_video)

        self.botao_playlist = QPushButton("Apenas Playlists")
        self.botao_playlist.setFixedSize(165, 42)
        self.botao_playlist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_playlist.clicked.connect(self.selecionar_playlist)

        layout_download = QVBoxLayout()
        layout_download.setSpacing(4)

        self.botao_download = QPushButton("Download")
        self.botao_download.setFixedSize(210, 46)
        self.botao_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_download.clicked.connect(self.iniciar_download)

        self.texto_status = QLabel("Pronto")
        self.texto_status.setObjectName("textoStatus")
        self.texto_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout_download.addWidget(self.botao_download)
        layout_download.addWidget(self.texto_status)

        layout_controles.addWidget(self.botao_video, alignment=Qt.AlignmentFlag.AlignTop)
        layout_controles.addWidget(self.botao_playlist, alignment=Qt.AlignmentFlag.AlignTop)
        layout_controles.addStretch()
        layout_controles.addLayout(layout_download)

        layout_principal.addLayout(layout_controles)
        layout_principal.addSpacing(6)

        layout_inferior = QHBoxLayout()
        layout_inferior.setSpacing(24)

        self.caixa_explorador = QFrame()
        self.caixa_explorador.setObjectName("caixaRoxa")
        self.caixa_explorador.setFixedWidth(400)
        layout_roxo = QVBoxLayout(self.caixa_explorador)
        layout_roxo.setContentsMargins(12, 12, 12, 12)
        layout_roxo.setSpacing(8)

        layout_topo_roxo = QHBoxLayout()
        self.texto_destino = QLabel(f"Destino: {os.path.basename(self.pasta_destino)}")
        self.texto_destino.setObjectName("textoDestino")

        self.botao_raiz = QPushButton("Raiz")
        self.botao_raiz.setObjectName("botaoRoxo")
        self.botao_raiz.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_raiz.clicked.connect(self.voltar_raiz)

        self.botao_nova_pasta = QPushButton("+ Nova Pasta")
        self.botao_nova_pasta.setObjectName("botaoRoxo")
        self.botao_nova_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_nova_pasta.clicked.connect(self.criar_pasta)

        layout_topo_roxo.addWidget(self.texto_destino)
        layout_topo_roxo.addStretch()
        layout_topo_roxo.addWidget(self.botao_raiz)
        layout_topo_roxo.addWidget(self.botao_nova_pasta)

        self.modelo_arquivos = QFileSystemModel()
        self.modelo_arquivos.setRootPath(self.pasta_raiz)
        self.modelo_arquivos.setReadOnly(False)
        self.modelo_arquivos.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self.modelo_arquivos.setNameFilters(["*.mp3", "*.m4a", "*.wav", "*.ogg"])
        self.modelo_arquivos.setNameFilterDisables(False)

        self.arvore_arquivos = QTreeView()
        self.arvore_arquivos.setObjectName("arvoreRoxa")
        self.arvore_arquivos.setModel(self.modelo_arquivos)
        self.arvore_arquivos.setRootIndex(self.modelo_arquivos.index(self.pasta_raiz))
        self.arvore_arquivos.setHeaderHidden(True)
        for coluna in range(1, 4):
            self.arvore_arquivos.hideColumn(coluna)

        self.arvore_arquivos.setMouseTracking(True)
        self.arvore_arquivos.viewport().setMouseTracking(True)
        self.arvore_arquivos.viewport().installEventFilter(self)
        self.arvore_arquivos.verticalScrollBar().valueChanged.connect(self.esconder_botoes_hover)
        self.arvore_arquivos.expanded.connect(self.esconder_botoes_hover)
        self.arvore_arquivos.collapsed.connect(self.esconder_botoes_hover)

        self.arvore_arquivos.setDragEnabled(True)
        self.arvore_arquivos.setAcceptDrops(True)
        self.arvore_arquivos.setDropIndicatorShown(True)
        self.arvore_arquivos.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.arvore_arquivos.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.arvore_arquivos.clicked.connect(self.selecionar_item)

        layout_roxo.addLayout(layout_topo_roxo)
        layout_roxo.addWidget(self.arvore_arquivos)

        layout_direita = QVBoxLayout()
        layout_direita.addStretch()

        self.caixa_player = QFrame()
        self.caixa_player.setObjectName("caixaPlayer")
        layout_player = QVBoxLayout(self.caixa_player)
        layout_player.setContentsMargins(8, 8, 8, 8)
        layout_player.setSpacing(10)

        self.label_titulo_musica = QLabel("Nenhuma música selecionada")
        self.label_titulo_musica.setObjectName("tituloMusica")

        self.label_artista_musica = QLabel("Passe o mouse em uma música para tocar")
        self.label_artista_musica.setObjectName("artistaMusica")

        layout_progresso = QHBoxLayout()
        layout_progresso.setSpacing(8)

        self.label_tempo_atual = QLabel("0:00")
        self.label_tempo_atual.setObjectName("tempoMusica")

        self.barra_tempo = QSlider(Qt.Orientation.Horizontal)
        self.barra_tempo.setObjectName("barraTempo")
        self.barra_tempo.setRange(0, 0)
        self.barra_tempo.sliderPressed.connect(self.iniciar_arrasto_tempo)
        self.barra_tempo.sliderReleased.connect(self.finalizar_arrasto_tempo)

        self.label_tempo_total = QLabel("0:00")
        self.label_tempo_total.setObjectName("tempoMusica")

        layout_progresso.addWidget(self.label_tempo_atual)
        layout_progresso.addWidget(self.barra_tempo, stretch=1)
        layout_progresso.addWidget(self.label_tempo_total)

        layout_botoes_player = QHBoxLayout()
        layout_botoes_player.setSpacing(12)

        self.icone_loop = self.carregar_icone(["loop.svg"])
        self.icone_mix = self.carregar_icone(["mix.svg"])
        self.icone_voltar = self.carregar_icone(["backward.png"])
        self.icone_play = self.carregar_icone(["play.png"])
        self.icone_pause = self.carregar_icone(["pause.png", "play.png"])
        self.icone_avancar = self.carregar_icone(["foward.png", "forward.png"])
        self.icone_volume = self.carregar_icone(["volume.svg"])

        self.botao_repetir = QPushButton()
        self.botao_repetir.setObjectName("botaoControle")
        self.botao_repetir.setFixedSize(42, 42)
        self.botao_repetir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_repetir.setToolTip("Repetir: Desligado")
        if not self.icone_loop.isNull():
            self.botao_repetir.setIcon(self.icone_loop)
            self.botao_repetir.setIconSize(QSize(20, 20))
        else:
            self.botao_repetir.setText("Loop")
        self.botao_repetir.clicked.connect(self.alternar_repetir)

        self.botao_aleatorio = QPushButton()
        self.botao_aleatorio.setObjectName("botaoControle")
        self.botao_aleatorio.setFixedSize(42, 42)
        self.botao_aleatorio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_aleatorio.setToolTip("Mix (Aleatório): Desligado")
        if not self.icone_mix.isNull():
            self.botao_aleatorio.setIcon(self.icone_mix)
            self.botao_aleatorio.setIconSize(QSize(20, 20))
        else:
            self.botao_aleatorio.setText("Mix")
        self.botao_aleatorio.clicked.connect(self.alternar_aleatorio)

        self.botao_anterior = QPushButton()
        self.botao_anterior.setObjectName("botaoControle")
        self.botao_anterior.setFixedSize(42, 42)
        self.botao_anterior.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_anterior.setToolTip("Anterior")
        if not self.icone_voltar.isNull():
            self.botao_anterior.setIcon(self.icone_voltar)
            self.botao_anterior.setIconSize(QSize(20, 20))
        else:
            self.botao_anterior.setText("<<")
        self.botao_anterior.clicked.connect(self.tocar_anterior)

        self.botao_play_pause = QPushButton()
        self.botao_play_pause.setObjectName("botaoPlayPrincipal")
        self.botao_play_pause.setFixedSize(52, 52)
        self.botao_play_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_play_pause.setToolTip("Tocar / Pausar")
        if not self.icone_play.isNull():
            self.botao_play_pause.setIcon(self.icone_play)
            self.botao_play_pause.setIconSize(QSize(24, 24))
        else:
            self.botao_play_pause.setText("Play")
        self.botao_play_pause.clicked.connect(self.alternar_play_pause)

        self.botao_proximo = QPushButton()
        self.botao_proximo.setObjectName("botaoControle")
        self.botao_proximo.setFixedSize(42, 42)
        self.botao_proximo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_proximo.setToolTip("Próxima")
        if not self.icone_avancar.isNull():
            self.botao_proximo.setIcon(self.icone_avancar)
            self.botao_proximo.setIconSize(QSize(20, 20))
        else:
            self.botao_proximo.setText(">>")
        self.botao_proximo.clicked.connect(self.tocar_proxima)

        self.botao_abrir_fila = QPushButton("☰")
        self.botao_abrir_fila.setObjectName("botaoListaPlayer")
        self.botao_abrir_fila.setFixedSize(42, 42)
        self.botao_abrir_fila.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_abrir_fila.setToolTip("Lista de reprodução")
        self.botao_abrir_fila.clicked.connect(self.alternar_painel_fila)

        self.botao_volume = QPushButton()
        self.botao_volume.setObjectName("botaoControle")
        self.botao_volume.setFixedSize(42, 42)
        self.botao_volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_volume.setToolTip("Volume")
        if not self.icone_volume.isNull():
            self.botao_volume.setIcon(self.icone_volume)
            self.botao_volume.setIconSize(QSize(20, 20))
        else:
            self.botao_volume.setText("Vol")
        self.botao_volume.clicked.connect(self.alternar_popup_volume)

        layout_botoes_player.addWidget(self.botao_repetir)
        layout_botoes_player.addWidget(self.botao_aleatorio)
        layout_botoes_player.addWidget(self.botao_anterior)
        layout_botoes_player.addWidget(self.botao_play_pause)
        layout_botoes_player.addWidget(self.botao_proximo)
        layout_botoes_player.addSpacing(10)
        layout_botoes_player.addWidget(self.botao_abrir_fila)
        layout_botoes_player.addWidget(self.botao_volume)
        layout_botoes_player.addStretch()

        layout_player.addWidget(self.label_titulo_musica)
        layout_player.addWidget(self.label_artista_musica)
        layout_player.addLayout(layout_progresso)
        layout_player.addLayout(layout_botoes_player)

        layout_direita.addWidget(self.caixa_player)

        layout_inferior.addWidget(self.caixa_explorador)
        layout_inferior.addLayout(layout_direita, stretch=1)

        layout_principal.addLayout(layout_inferior, stretch=1)

    def montar_painel_fila_flutuante(self):
        self.painel_fila = QFrame(self)
        self.painel_fila.setObjectName("painelFila")
        self.painel_fila.hide()

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(24)
        sombra.setOffset(0, 6)
        sombra.setColor(QColor(0, 0, 0, 170))
        self.painel_fila.setGraphicsEffect(sombra)

        layout_fila = QVBoxLayout(self.painel_fila)
        layout_fila.setContentsMargins(16, 14, 16, 14)
        layout_fila.setSpacing(10)

        layout_cabecalho = QHBoxLayout()
        titulo_lista = QLabel("Lista")
        titulo_lista.setObjectName("tituloListaFlutuante")

        botao_fechar_lista = QPushButton("✕")
        botao_fechar_lista.setObjectName("botaoFecharLista")
        botao_fechar_lista.setFixedSize(28, 28)
        botao_fechar_lista.setCursor(Qt.CursorShape.PointingHandCursor)
        botao_fechar_lista.clicked.connect(self.painel_fila.hide)

        layout_cabecalho.addWidget(titulo_lista)
        layout_cabecalho.addStretch()
        layout_cabecalho.addWidget(botao_fechar_lista)

        self.lista_fila = QListWidget()
        self.lista_fila.setObjectName("listaUnificada")
        self.lista_fila.setDragEnabled(True)
        self.lista_fila.setAcceptDrops(True)
        self.lista_fila.setDropIndicatorShown(True)
        self.lista_fila.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lista_fila.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.lista_fila.model().rowsMoved.connect(self.sincronizar_ordem_fila)
        self.lista_fila.itemDoubleClicked.connect(self.tocar_item_lista_unificada)

        layout_fila.addLayout(layout_cabecalho)
        layout_fila.addWidget(self.lista_fila, stretch=1)

    def montar_popup_volume(self):
        self.popup_volume = QFrame(self)
        self.popup_volume.setObjectName("popupVolume")
        self.popup_volume.setFixedSize(46, 155)
        self.popup_volume.hide()

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(16)
        sombra.setOffset(0, 4)
        sombra.setColor(QColor(0, 0, 0, 150))
        self.popup_volume.setGraphicsEffect(sombra)

        layout_vol = QVBoxLayout(self.popup_volume)
        layout_vol.setContentsMargins(6, 10, 6, 10)
        layout_vol.setSpacing(6)

        self.label_valor_volume = QLabel("85%")
        self.label_valor_volume.setObjectName("textoVolume")
        self.label_valor_volume.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.barra_volume = QSlider(Qt.Orientation.Vertical)
        self.barra_volume.setObjectName("barraVolume")
        self.barra_volume.setRange(0, 100)
        self.barra_volume.setValue(85)
        self.barra_volume.valueChanged.connect(self.alterar_volume)

        layout_vol.addWidget(self.label_valor_volume)
        layout_vol.addWidget(self.barra_volume, alignment=Qt.AlignmentFlag.AlignHCenter)

    def montar_botoes_hover(self):
        self.barra_hover = QWidget(self.arvore_arquivos.viewport())
        self.barra_hover.setObjectName("barraHover")
        self.barra_hover.installEventFilter(self)
        self.barra_hover.hide()

        layout_hover = QHBoxLayout(self.barra_hover)
        layout_hover.setContentsMargins(4, 1, 4, 1)
        layout_hover.setSpacing(4)

        self.botao_tocar_hover = QPushButton("▶")
        self.botao_tocar_hover.setObjectName("botaoHoverTocar")
        self.botao_tocar_hover.setFixedSize(24, 22)
        self.botao_tocar_hover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_tocar_hover.setToolTip("Tocar agora")
        self.botao_tocar_hover.clicked.connect(self.ao_clicar_tocar_agora)

        self.botao_fila_hover = QPushButton("☰+")
        self.botao_fila_hover.setObjectName("botaoHoverFila")
        self.botao_fila_hover.setFixedSize(28, 22)
        self.botao_fila_hover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_fila_hover.setToolTip("Adicionar à lista de reprodução")
        self.botao_fila_hover.clicked.connect(self.ao_clicar_adicionar_fila)

        layout_hover.addWidget(self.botao_tocar_hover)
        layout_hover.addWidget(self.botao_fila_hover)
        self.barra_hover.adjustSize()

    def montar_aba_sugestoes(self):
        self.aba_sugestoes = QFrame(self)
        self.aba_sugestoes.setObjectName("abaSugestoes")
        self.aba_sugestoes.hide()

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(24)
        sombra.setOffset(0, 8)
        sombra.setColor(QColor(0, 0, 0, 160))
        self.aba_sugestoes.setGraphicsEffect(sombra)

        self.layout_aba = QVBoxLayout(self.aba_sugestoes)
        self.layout_aba.setContentsMargins(10, 10, 10, 10)
        self.layout_aba.setSpacing(6)

        self.titulo_aba = QLabel("Resultados relacionados")
        self.titulo_aba.setObjectName("tituloAba")
        self.layout_aba.addWidget(self.titulo_aba)

        self.container_itens = QWidget()
        self.container_itens.setObjectName("containerItens")
        self.layout_itens = QVBoxLayout(self.container_itens)
        self.layout_itens.setContentsMargins(0, 0, 0, 0)
        self.layout_itens.setSpacing(6)
        self.layout_aba.addWidget(self.container_itens)

    def aplicar_estilo(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #C5BFE3;
                font-family: Arial, sans-serif;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #000000;
                color: #FFFFFF;
                border: none;
                padding: 0 14px;
                font-size: 15px;
            }
            QFrame#abaSugestoes {
                background-color: #2A3038;
                border: 1px solid #434B56;
            }
            QWidget#containerItens {
                background-color: transparent;
            }
            QLabel#tituloAba {
                background-color: transparent;
                color: #C6D4DF;
                font-weight: bold;
                font-size: 13px;
                padding-bottom: 2px;
            }
            QFrame#cardSugestao {
                background-color: #363E48;
                border: none;
            }
            QFrame#cardSugestao:hover {
                background-color: #46515E;
            }
            QLabel#thumbSugestao {
                background-color: #1B2026;
                color: #8F98A0;
                font-size: 11px;
            }
            QLabel#tituloSugestao {
                background-color: transparent;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
            }
            QLabel#detalheSugestao {
                background-color: transparent;
                color: #8F98A0;
                font-size: 12px;
            }
            QPushButton#botaoDownload {
                background-color: #22B14C;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 16px;
                border: none;
            }
            QPushButton#botaoDownload:hover {
                background-color: #1D9941;
            }
            QPushButton#botaoDownload:disabled {
                background-color: #6E9E7B;
            }
            QFrame#caixaRoxa {
                background-color: #9C419E;
                border: none;
            }
            QLabel#textoDestino {
                background-color: transparent;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton#botaoRoxo {
                background-color: #7D2E7F;
                color: #FFFFFF;
                border: 1px solid #B865BA;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton#botaoRoxo:hover {
                background-color: #69246B;
            }
            QTreeView#arvoreRoxa {
                background-color: #9C419E;
                color: #FFFFFF;
                border: none;
                outline: none;
            }
            QTreeView#arvoreRoxa::item {
                padding: 5px;
            }
            QTreeView#arvoreRoxa::item:selected {
                background-color: #7D2E7F;
                color: #FFFFFF;
            }
            QTreeView#arvoreRoxa::item:hover {
                background-color: #8A358C;
            }
            QWidget#barraHover {
                background-color: #7D2E7F;
                border-radius: 4px;
            }
            QPushButton#botaoHoverTocar {
                background-color: #FF7F27;
                color: #000000;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton#botaoHoverTocar:hover {
                background-color: #FFA04D;
            }
            QPushButton#botaoHoverFila {
                background-color: #FFF200;
                color: #000000;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton#botaoHoverFila:hover {
                background-color: #FFF766;
            }
            QLabel#textoStatus {
                background-color: transparent;
                color: #2E294E;
                font-weight: bold;
                font-size: 13px;
            }
            QFrame#caixaPlayer {
                background-color: transparent;
                border: none;
            }
            QLabel#tituloMusica {
                background-color: transparent;
                color: #1B1734;
                font-weight: bold;
                font-size: 17px;
            }
            QLabel#artistaMusica {
                background-color: transparent;
                color: #463F6E;
                font-weight: bold;
                font-size: 13px;
            }
            QLabel#tempoMusica {
                background-color: transparent;
                color: #2E294E;
                font-weight: bold;
                font-size: 11px;
            }
            QSlider#barraTempo {
                background-color: transparent;
            }
            QSlider#barraTempo::groove:horizontal {
                height: 5px;
                background: #9B92C4;
                border-radius: 2px;
            }
            QSlider#barraTempo::sub-page:horizontal {
                background: #9C419E;
                border-radius: 2px;
            }
            QSlider#barraTempo::handle:horizontal {
                background: #2E294E;
                width: 13px;
                height: 13px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QPushButton#botaoControle {
                background-color: #9A92C4;
                color: #1B1734;
                border: 1px solid #7E75AD;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#botaoControle:hover {
                background-color: #887FB8;
            }
            QPushButton#botaoPlayPrincipal {
                background-color: #9A92C4;
                color: #1B1734;
                border: 1px solid #7E75AD;
                border-radius: 26px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton#botaoPlayPrincipal:hover {
                background-color: #887FB8;
            }
            QPushButton#botaoListaPlayer {
                background-color: #9A92C4;
                color: #1B1734;
                border: 1px solid #7E75AD;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton#botaoListaPlayer:hover {
                background-color: #887FB8;
            }
            QFrame#painelFila {
                background-color: #7D7D82;
                border: 1px solid #58585E;
                border-radius: 6px;
            }
            QLabel#tituloListaFlutuante {
                background-color: transparent;
                color: #141416;
                font-weight: bold;
                font-size: 18px;
            }
            QPushButton#botaoFecharLista {
                background-color: #66666B;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton#botaoFecharLista:hover {
                background-color: #4E4E52;
            }
            QListWidget#listaUnificada {
                background-color: #6E6E73;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                outline: none;
            }
            QListWidget#listaUnificada::item {
                padding: 8px 10px;
                border-bottom: 1px solid #5E5E63;
            }
            QFrame#popupVolume {
                background-color: #2B2B33;
                border: 1px solid #4A4A57;
                border-radius: 6px;
            }
            QLabel#textoVolume {
                background-color: transparent;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: bold;
            }
            QSlider#barraVolume {
                background-color: transparent;
            }
            QSlider#barraVolume::groove:vertical {
                width: 5px;
                background: #4E4E5C;
                border-radius: 2px;
            }
            QSlider#barraVolume::add-page:vertical {
                background: #9C419E;
                border-radius: 2px;
            }
            QSlider#barraVolume::handle:vertical {
                background: #FFFFFF;
                height: 12px;
                width: 12px;
                margin: 0 -4px;
                border-radius: 6px;
            }
        """)
        self.botao_download.setObjectName("botaoDownload")
        self.style().unpolish(self.botao_download)
        self.style().polish(self.botao_download)

    def eventFilter(self, objeto, evento):
        if objeto == self.arvore_arquivos.viewport():
            if evento.type() == QEvent.Type.MouseMove:
                indice = self.arvore_arquivos.indexAt(evento.position().toPoint())
                if indice.isValid():
                    self.caminho_hover = self.modelo_arquivos.filePath(indice)
                    retangulo = self.arvore_arquivos.visualRect(indice)
                    largura_viewport = self.arvore_arquivos.viewport().width()
                    pos_x = max(4, largura_viewport - self.barra_hover.width() - 4)
                    pos_y = retangulo.y() + (retangulo.height() - self.barra_hover.height()) // 2
                    self.barra_hover.move(pos_x, pos_y)
                    self.barra_hover.show()
                    self.barra_hover.raise_()
                else:
                    self.esconder_botoes_hover()
            elif evento.type() == QEvent.Type.Leave:
                if not self.barra_hover.underMouse():
                    self.esconder_botoes_hover()

        elif objeto == self.barra_hover:
            if evento.type() == QEvent.Type.Leave:
                if not self.arvore_arquivos.viewport().underMouse():
                    self.esconder_botoes_hover()

        if evento.type() == QEvent.Type.MouseButtonPress:
            posicao_global = evento.globalPosition().toPoint()

            if self.aba_sugestoes.isVisible():
                dentro_barra = self.barra_pesquisa.rect().contains(
                    self.barra_pesquisa.mapFromGlobal(posicao_global)
                )
                dentro_aba = self.aba_sugestoes.rect().contains(
                    self.aba_sugestoes.mapFromGlobal(posicao_global)
                )
                if not dentro_barra and not dentro_aba:
                    self.aba_sugestoes.hide()

            if self.popup_volume.isVisible():
                dentro_vol = self.popup_volume.rect().contains(
                    self.popup_volume.mapFromGlobal(posicao_global)
                )
                dentro_btn_vol = self.botao_volume.rect().contains(
                    self.botao_volume.mapFromGlobal(posicao_global)
                )
                if not dentro_vol and not dentro_btn_vol:
                    self.popup_volume.hide()

        elif evento.type() == QEvent.Type.KeyPress:
            if evento.key() == Qt.Key.Key_Escape:
                if self.aba_sugestoes.isVisible():
                    self.aba_sugestoes.hide()
                if self.popup_volume.isVisible():
                    self.popup_volume.hide()
                if self.painel_fila.isVisible():
                    self.painel_fila.hide()

        return super().eventFilter(objeto, evento)

    def esconder_botoes_hover(self):
        self.barra_hover.hide()
        self.caminho_hover = None

    def listar_audios_pasta(self, pasta):
        extensoes = (".mp3", ".m4a", ".wav", ".ogg")
        if not os.path.isdir(pasta):
            return []
        arquivos = [
            os.path.join(pasta, nome)
            for nome in os.listdir(pasta)
            if nome.lower().endswith(extensoes) and os.path.isfile(os.path.join(pasta, nome))
        ]
        arquivos.sort(key=lambda caminho: os.path.basename(caminho).lower())
        return arquivos

    def ao_clicar_tocar_agora(self):
        if not self.caminho_hover:
            return
        alvo = self.caminho_hover
        if os.path.isdir(alvo):
            musicas = self.listar_audios_pasta(alvo)
            if not musicas:
                self.texto_status.setText("Pasta sem músicas.")
                return
            if self.modo_aleatorio:
                random.shuffle(musicas)
            self.tocar_agora_arquivo(musicas[0], musicas[1:])
        else:
            pasta = os.path.dirname(alvo)
            todas = self.listar_audios_pasta(pasta)
            outras = [m for m in todas if os.path.normcase(m) != os.path.normcase(alvo)]
            if self.modo_aleatorio:
                random.shuffle(outras)
            else:
                indice_alvo = next(
                    (i for i, m in enumerate(todas) if os.path.normcase(m) == os.path.normcase(alvo)),
                    0,
                )
                outras = todas[indice_alvo + 1 :] + todas[:indice_alvo]
            self.tocar_agora_arquivo(alvo, outras)

    def tocar_agora_arquivo(self, arquivo, lista_seguinte):
        self.historico_tocadas.clear()
        self.adicionadas_manualmente.clear()
        self.proximas_musicas = list(lista_seguinte)
        self.reproduzir_caminho(arquivo)
        self.atualizar_interface_fila()

    def ao_clicar_adicionar_fila(self):
        if not self.caminho_hover:
            return
        alvo = self.caminho_hover
        if os.path.isdir(alvo):
            musicas = self.listar_audios_pasta(alvo)
        else:
            musicas = [alvo]

        if not musicas:
            self.texto_status.setText("Nenhuma música para adicionar.")
            return

        if not self.musica_atual:
            self.tocar_agora_arquivo(musicas[0], musicas[1:])
            return

        for musica in reversed(musicas):
            self.proximas_musicas = [
                m for m in self.proximas_musicas if os.path.normcase(m) != os.path.normcase(musica)
            ]
            self.proximas_musicas.insert(0, musica)
            self.adicionadas_manualmente.add(os.path.normcase(musica))

        self.atualizar_interface_fila()
        nome_exibido = os.path.basename(alvo)
        self.texto_status.setText(f"Na fila: {nome_exibido[:30]}")

    def reproduzir_caminho(self, caminho):
        if not caminho or not os.path.isfile(caminho):
            return
        self.musica_atual = caminho
        self.adicionadas_manualmente.discard(os.path.normcase(caminho))
        nome_arquivo = os.path.splitext(os.path.basename(caminho))[0]
        nome_pasta = os.path.basename(os.path.dirname(caminho))

        self.label_titulo_musica.setText(nome_arquivo)
        self.label_artista_musica.setText(nome_pasta)
        self.tocador.setSource(QUrl.fromLocalFile(caminho))
        self.tocador.play()
        self.atualizar_interface_fila()

    def ao_atualizar_metadados(self):
        metadados = self.tocador.metaData()
        artista = (
            metadados.stringValue(QMediaMetaData.Key.ContributingArtist)
            or metadados.stringValue(QMediaMetaData.Key.Author)
            or metadados.stringValue(QMediaMetaData.Key.AlbumArtist)
        )
        if artista and self.musica_atual:
            self.label_artista_musica.setText(artista)

    def alternar_play_pause(self):
        if not self.musica_atual:
            if self.proximas_musicas:
                proxima = self.proximas_musicas.pop(0)
                self.reproduzir_caminho(proxima)
            return

        if self.tocador.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.tocador.pause()
        else:
            self.tocador.play()

    def ao_mudar_estado_reproducao(self, estado):
        if estado == QMediaPlayer.PlaybackState.PlayingState:
            if not self.icone_pause.isNull():
                self.botao_play_pause.setIcon(self.icone_pause)
            else:
                self.botao_play_pause.setText("Pause")
        else:
            if not self.icone_play.isNull():
                self.botao_play_pause.setIcon(self.icone_play)
            else:
                self.botao_play_pause.setText("Play")

    def ao_mudar_status_midia(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.modo_repetir == "musica" and self.musica_atual:
                self.tocador.setPosition(0)
                self.tocador.play()
            else:
                self.avancar_proxima_automatico()

    def avancar_proxima_automatico(self):
        if self.musica_atual:
            self.historico_tocadas.append(self.musica_atual)

        if self.proximas_musicas:
            proxima = self.proximas_musicas.pop(0)
            self.reproduzir_caminho(proxima)
        elif self.modo_repetir == "lista" and self.historico_tocadas:
            reinicio = list(self.historico_tocadas)
            self.historico_tocadas.clear()
            if self.modo_aleatorio:
                random.shuffle(reinicio)
            primeira = reinicio.pop(0)
            self.proximas_musicas = reinicio
            self.reproduzir_caminho(primeira)
        else:
            self.musica_atual = None
            self.label_titulo_musica.setText("Fim da lista de reprodução")
            self.label_artista_musica.setText("")
            self.atualizar_interface_fila()

    def tocar_proxima(self):
        if not self.musica_atual and not self.proximas_musicas:
            return
        self.avancar_proxima_automatico()

    def tocar_anterior(self):
        if not self.musica_atual:
            return
        if self.tocador.position() > 3000:
            self.tocador.setPosition(0)
            return
        if self.historico_tocadas:
            self.proximas_musicas.insert(0, self.musica_atual)
            anterior = self.historico_tocadas.pop()
            self.reproduzir_caminho(anterior)
        else:
            self.tocador.setPosition(0)

    def alternar_aleatorio(self):
        self.modo_aleatorio = not self.modo_aleatorio
        self.atualizar_visual_controles_player()

        if not self.proximas_musicas:
            return

        fixadas = [
            m for m in self.proximas_musicas if os.path.normcase(m) in self.adicionadas_manualmente
        ]
        restantes = [
            m for m in self.proximas_musicas if os.path.normcase(m) not in self.adicionadas_manualmente
        ]

        if self.modo_aleatorio:
            random.shuffle(restantes)
        else:
            restantes.sort(key=lambda caminho: os.path.basename(caminho).lower())

        self.proximas_musicas = fixadas + restantes
        self.atualizar_interface_fila()

    def alternar_repetir(self):
        if self.modo_repetir == "desligado":
            self.modo_repetir = "lista"
        elif self.modo_repetir == "lista":
            self.modo_repetir = "musica"
        else:
            self.modo_repetir = "desligado"
        self.atualizar_visual_controles_player()

    def atualizar_visual_controles_player(self):
        if self.modo_aleatorio:
            self.botao_aleatorio.setStyleSheet(
                "background-color: #9C419E; border: 2px solid #000000; border-radius: 6px;"
            )
            self.botao_aleatorio.setToolTip("Mix (Aleatório): Ligado")
        else:
            self.botao_aleatorio.setStyleSheet("")
            self.botao_aleatorio.setToolTip("Mix (Aleatório): Desligado")

        if self.modo_repetir == "desligado":
            self.botao_repetir.setStyleSheet("")
            self.botao_repetir.setToolTip("Repetir: Desligado")
        elif self.modo_repetir == "lista":
            self.botao_repetir.setStyleSheet(
                "background-color: #FF7F27; border: 2px solid #000000; border-radius: 6px;"
            )
            self.botao_repetir.setToolTip("Repetir: Lista inteira (Laranja)")
        else:
            self.botao_repetir.setStyleSheet(
                "background-color: #FFF200; border: 2px solid #000000; border-radius: 6px;"
            )
            self.botao_repetir.setToolTip("Repetir: Música atual (Amarelo)")

    def reposicionar_painel_fila(self):
        pos_explorador = self.caixa_explorador.mapTo(self, QPoint(0, 0))
        x_inicio = pos_explorador.x() + self.caixa_explorador.width() + 24
        largura = max(320, self.width() - x_inicio - 35)
        y_inicio = self.barra_pesquisa.mapTo(self, QPoint(0, 0)).y()
        y_fim = self.caixa_player.mapTo(self, QPoint(0, 0)).y() - 10
        altura = max(240, y_fim - y_inicio)
        self.painel_fila.setGeometry(x_inicio, y_inicio, largura, altura)
        self.painel_fila.raise_()

    def alternar_painel_fila(self):
        if self.painel_fila.isVisible():
            self.painel_fila.hide()
        else:
            self.atualizar_interface_fila()
            self.reposicionar_painel_fila()
            self.painel_fila.show()

    def alternar_popup_volume(self):
        if self.popup_volume.isVisible():
            self.popup_volume.hide()
        else:
            pos_btn = self.botao_volume.mapTo(self, QPoint(0, 0))
            x = pos_btn.x() + (self.botao_volume.width() - self.popup_volume.width()) // 2
            y = pos_btn.y() - self.popup_volume.height() - 6
            self.popup_volume.move(x, y)
            self.popup_volume.show()
            self.popup_volume.raise_()

    def alterar_volume(self, valor):
        self.saida_audio.setVolume(valor / 100.0)
        self.label_valor_volume.setText(f"{valor}%")

    def atualizar_interface_fila(self):
        self.lista_fila.blockSignals(True)
        self.lista_fila.clear()
        item_destaque = None

        for indice, caminho in enumerate(self.historico_tocadas):
            nome = os.path.splitext(os.path.basename(caminho))[0]
            item = QListWidgetItem(nome)
            item.setData(Qt.ItemDataRole.UserRole, ("historico", indice, caminho))
            item.setForeground(QColor("#CFCFD4"))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.lista_fila.addItem(item)

        if self.musica_atual:
            nome_atual = os.path.splitext(os.path.basename(self.musica_atual))[0]
            item_atual = QListWidgetItem(nome_atual)
            item_atual.setData(Qt.ItemDataRole.UserRole, ("atual", 0, self.musica_atual))
            item_atual.setBackground(QColor("#FFF200"))
            item_atual.setForeground(QColor("#000000"))
            fonte_negrito = QFont()
            fonte_negrito.setBold(True)
            item_atual.setFont(fonte_negrito)
            item_atual.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.lista_fila.addItem(item_atual)
            item_destaque = item_atual

        for indice, caminho in enumerate(self.proximas_musicas):
            nome = os.path.splitext(os.path.basename(caminho))[0]
            item = QListWidgetItem(nome)
            item.setData(Qt.ItemDataRole.UserRole, ("proxima", indice, caminho))
            item.setForeground(QColor("#FFFFFF"))
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            self.lista_fila.addItem(item)

        self.lista_fila.blockSignals(False)
        if item_destaque:
            self.lista_fila.scrollToItem(item_destaque)

    def sincronizar_ordem_fila(self):
        novas_proximas = []
        for linha in range(self.lista_fila.count()):
            dados = self.lista_fila.item(linha).data(Qt.ItemDataRole.UserRole)
            if dados and dados[0] == "proxima":
                novas_proximas.append(dados[2])
        self.proximas_musicas = novas_proximas
        QTimer.singleShot(0, self.atualizar_interface_fila)

    def tocar_item_lista_unificada(self, item):
        dados = item.data(Qt.ItemDataRole.UserRole)
        if not dados:
            return
        tipo, indice, caminho = dados
        if tipo == "proxima":
            if self.musica_atual:
                self.historico_tocadas.append(self.musica_atual)
            self.proximas_musicas = self.proximas_musicas[indice + 1 :]
            self.reproduzir_caminho(caminho)
        elif tipo == "historico":
            if self.musica_atual:
                self.proximas_musicas.insert(0, self.musica_atual)
            self.historico_tocadas = self.historico_tocadas[:indice]
            self.reproduzir_caminho(caminho)

    def iniciar_arrasto_tempo(self):
        self.arrastando_tempo = True

    def finalizar_arrasto_tempo(self):
        self.arrastando_tempo = False
        self.tocador.setPosition(self.barra_tempo.value())

    def ao_mudar_posicao(self, posicao):
        if not self.arrastando_tempo:
            self.barra_tempo.setValue(posicao)
        self.label_tempo_atual.setText(self.formatar_duracao(posicao // 1000))

    def ao_mudar_duracao(self, duracao):
        self.barra_tempo.setRange(0, duracao)
        self.label_tempo_total.setText(self.formatar_duracao(duracao // 1000))

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        if self.aba_sugestoes.isVisible():
            self.reposicionar_aba_sugestoes(self.aba_sugestoes.height())
        if self.painel_fila.isVisible():
            self.reposicionar_painel_fila()
        if self.popup_volume.isVisible():
            self.popup_volume.hide()

    def reposicionar_aba_sugestoes(self, altura):
        pos = self.barra_pesquisa.mapTo(self, QPoint(0, self.barra_pesquisa.height()))
        self.aba_sugestoes.setGeometry(pos.x(), pos.y(), self.barra_pesquisa.width(), altura)
        self.aba_sugestoes.raise_()

    def limpar_cards_sugestao(self):
        self.cards_sugestao.clear()
        while self.layout_itens.count():
            item = self.layout_itens.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def ao_digitar_pesquisa(self, texto):
        if self.ignorar_alteracao_texto:
            return
        self.link_escolhido = None
        termo = texto.strip()
        if len(termo) < 2:
            self.temporizador_busca.stop()
            self.aba_sugestoes.hide()
            return
        self.temporizador_busca.start(550)

    def disparar_busca_relacionados(self):
        termo = self.barra_pesquisa.text().strip()
        if not termo:
            return

        self.contador_busca += 1
        id_busca = self.contador_busca

        self.limpar_cards_sugestao()
        self.titulo_aba.setText("Buscando resultados relacionados...")
        self.reposicionar_aba_sugestoes(46)
        self.aba_sugestoes.show()

        thread = threading.Thread(
            target=self.buscar_opcoes_youtube,
            args=(id_busca, termo, self.modo_filtro),
            daemon=True,
        )
        thread.start()

    def formatar_duracao(self, segundos):
        if not segundos or segundos < 0:
            return "0:00"
        segundos = int(segundos)
        minutos, seg = divmod(segundos, 60)
        horas, minutos = divmod(minutos, 60)
        if horas > 0:
            return f"{horas}:{minutos:02d}:{seg:02d}"
        return f"{minutos}:{seg:02d}"

    def extrair_url_thumb(self, entrada):
        if entrada.get("thumbnail"):
            return entrada["thumbnail"]
        thumbs = entrada.get("thumbnails") or []
        if thumbs:
            return thumbs[0].get("url", "")
        id_video = entrada.get("id", "")
        if len(id_video) == 11:
            return f"https://i.ytimg.com/vi/{id_video}/mqdefault.jpg"
        return ""

    def buscar_opcoes_youtube(self, id_busca, termo, modo):
        try:
            eh_link = termo.startswith(("http://", "https://"))
            resultados = []

            if eh_link:
                opcoes_link = {"quiet": True, "no_warnings": True, "extract_flat": True}
                with yt_dlp.YoutubeDL(opcoes_link) as ydl:
                    info = ydl.extract_info(termo, download=False)

                if info:
                    titulo_base = info.get("title") or "Link informado"
                    url_base = info.get("webpage_url") or termo
                    canal_base = info.get("uploader") or info.get("channel") or "YouTube"
                    duracao_base = self.formatar_duracao(info.get("duration"))
                    qtd_itens = info.get("playlist_count") or len(info.get("entries") or [])

                    if qtd_itens and modo == "playlist":
                        detalhe_base = f"{canal_base} • Playlist ({qtd_itens} vídeos)"
                    elif duracao_base != "0:00":
                        detalhe_base = f"{canal_base} • {duracao_base}"
                    else:
                        detalhe_base = canal_base

                    resultados.append(
                        {
                            "titulo": titulo_base,
                            "detalhe": detalhe_base,
                            "url": url_base,
                            "thumb": self.extrair_url_thumb(info),
                        }
                    )

                    if titulo_base and titulo_base != "Link informado":
                        resultados.extend(self.pesquisar_lista(titulo_base, modo, limite=4))
            else:
                resultados = self.pesquisar_lista(termo, modo, limite=5)

            unicos = []
            urls_vistas = set()
            for item in resultados:
                if item["url"] and item["url"] not in urls_vistas:
                    urls_vistas.add(item["url"])
                    unicos.append(item)

            self.sinal_resultados.emit(id_busca, unicos[:5])

            for indice, item in enumerate(unicos[:5]):
                url_thumb = item.get("thumb")
                if url_thumb:
                    try:
                        with urlopen(url_thumb, timeout=5) as resposta:
                            dados_img = resposta.read()
                        self.sinal_thumbnail.emit(id_busca, indice, dados_img)
                    except Exception:
                        pass

        except Exception:
            self.sinal_resultados.emit(id_busca, [])

    def pesquisar_lista(self, consulta, modo, limite=5):
        itens = []
        if modo == "video":
            opcoes = {"quiet": True, "no_warnings": True, "extract_flat": True}
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(f"ytsearch{limite}:{consulta}", download=False)
                for entrada in info.get("entries") or []:
                    if not entrada:
                        continue
                    canal = entrada.get("uploader") or entrada.get("channel") or "YouTube"
                    duracao = self.formatar_duracao(entrada.get("duration"))
                    detalhe = f"{canal} • {duracao}" if duracao != "0:00" else canal
                    url_item = entrada.get("url") or f"https://www.youtube.com/watch?v={entrada.get('id')}"
                    itens.append(
                        {
                            "titulo": entrada.get("title", "Sem título"),
                            "detalhe": detalhe,
                            "url": url_item,
                            "thumb": self.extrair_url_thumb(entrada),
                        }
                    )
        else:
            url_busca = (
                f"https://www.youtube.com/results?search_query={quote_plus(consulta)}&sp=EgIQAw%3D%3D"
            )
            opcoes = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "playlistend": limite,
            }
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(url_busca, download=False)
                for entrada in info.get("entries") or []:
                    if not entrada:
                        continue
                    canal = entrada.get("uploader") or entrada.get("channel") or "Playlist"
                    qtd = entrada.get("playlist_count")
                    detalhe = f"{canal} • {qtd} vídeos" if qtd else f"{canal} • Playlist"
                    itens.append(
                        {
                            "titulo": entrada.get("title", "Playlist"),
                            "detalhe": detalhe,
                            "url": entrada.get("url"),
                            "thumb": self.extrair_url_thumb(entrada),
                        }
                    )
        return itens

    def preencher_sugestoes(self, id_busca, itens):
        if id_busca != self.contador_busca:
            return

        self.limpar_cards_sugestao()

        if not itens:
            self.titulo_aba.setText("Nenhum resultado encontrado")
            self.reposicionar_aba_sugestoes(46)
            return

        rotulo = "Vídeos relacionados" if self.modo_filtro == "video" else "Playlists relacionadas"
        self.titulo_aba.setText(rotulo)

        for item in itens:
            card = ItemSugestao(item)
            card.clicado.connect(self.selecionar_sugestao)
            self.layout_itens.addWidget(card)
            self.cards_sugestao.append(card)

        altura_total = 44 + (len(itens) * 74)
        self.reposicionar_aba_sugestoes(altura_total)
        self.aba_sugestoes.show()

    def aplicar_thumbnail(self, id_busca, indice, dados_imagem):
        if id_busca != self.contador_busca:
            return
        if 0 <= indice < len(self.cards_sugestao):
            self.cards_sugestao[indice].definir_thumbnail(dados_imagem)

    def selecionar_sugestao(self, dados):
        self.link_escolhido = dados.get("url")
        self.ignorar_alteracao_texto = True
        self.barra_pesquisa.setText(dados.get("titulo", ""))
        self.ignorar_alteracao_texto = False
        self.aba_sugestoes.hide()
        self.texto_status.setText(f"Selecionado: {dados.get('titulo', '')[:35]}")

    def atualizar_botoes_filtro(self):
        if self.modo_filtro == "video":
            self.botao_video.setStyleSheet(
                "background-color: #00A2E8; color: #FFFFFF; font-weight: bold; border: 3px solid #000000;"
            )
            self.botao_playlist.setStyleSheet(
                "background-color: #FFF200; color: #000000; font-weight: bold; border: 3px solid transparent;"
            )
        else:
            self.botao_video.setStyleSheet(
                "background-color: #00A2E8; color: #FFFFFF; font-weight: bold; border: 3px solid transparent;"
            )
            self.botao_playlist.setStyleSheet(
                "background-color: #FFF200; color: #000000; font-weight: bold; border: 3px solid #000000;"
            )

    def selecionar_video(self):
        self.modo_filtro = "video"
        self.atualizar_botoes_filtro()
        if len(self.barra_pesquisa.text().strip()) >= 2:
            self.disparar_busca_relacionados()

    def selecionar_playlist(self):
        self.modo_filtro = "playlist"
        self.atualizar_botoes_filtro()
        if len(self.barra_pesquisa.text().strip()) >= 2:
            self.disparar_busca_relacionados()

    def selecionar_item(self, indice):
        caminho = self.modelo_arquivos.filePath(indice)
        if os.path.isdir(caminho):
            self.pasta_destino = caminho
        else:
            self.pasta_destino = os.path.dirname(caminho)
        self.texto_destino.setText(f"Destino: {os.path.basename(self.pasta_destino)}")

    def voltar_raiz(self):
        self.pasta_destino = self.pasta_raiz
        self.arvore_arquivos.clearSelection()
        self.texto_destino.setText(f"Destino: {os.path.basename(self.pasta_destino)}")

    def criar_pasta(self):
        nome, confirmado = QInputDialog.getText(self, "Nova Pasta", "Nome da pasta:")
        if confirmado and nome.strip():
            nova_pasta = os.path.join(self.pasta_destino, nome.strip())
            os.makedirs(nova_pasta, exist_ok=True)
            self.pasta_destino = nova_pasta
            self.texto_destino.setText(f"Destino: {os.path.basename(self.pasta_destino)}")

    def iniciar_download(self):
        self.aba_sugestoes.hide()
        termo = self.link_escolhido or self.barra_pesquisa.text().strip()
        if not termo:
            self.texto_status.setText("Digite um nome ou cole um link.")
            return

        self.botao_download.setEnabled(False)
        self.texto_status.setText("Processando...")

        tarefa = threading.Thread(
            target=self.executar_download,
            args=(termo, self.modo_filtro, self.pasta_destino),
            daemon=True,
        )
        tarefa.start()

    def executar_download(self, termo, modo, destino):
        try:
            eh_link = termo.startswith(("http://", "https://"))

            if modo == "video":
                alvo = termo if eh_link else f"ytsearch1:{termo}"
                opcoes = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(destino, "%(title)s.%(ext)s"),
                    "noplaylist": True,
                    "playlist_items": "1",
                    "quiet": True,
                    "no_warnings": True,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        },
                    ],
                }
                self.sinal_status.emit("Baixando áudio...")
                with yt_dlp.YoutubeDL(opcoes) as ydl:
                    ydl.download([alvo])

            else:
                if eh_link:
                    alvo = termo
                else:
                    self.sinal_status.emit("Buscando playlist...")
                    url_busca = (
                        f"https://www.youtube.com/results?search_query={quote_plus(termo)}&sp=EgIQAw%3D%3D"
                    )
                    opcoes_busca = {
                        "quiet": True,
                        "extract_flat": True,
                        "playlistend": 1,
                    }
                    with yt_dlp.YoutubeDL(opcoes_busca) as ydl_busca:
                        info_busca = ydl_busca.extract_info(url_busca, download=False)
                        entradas = info_busca.get("entries") or []
                        if not entradas:
                            self.sinal_status.emit("Nenhuma playlist encontrada.")
                            self.sinal_concluido.emit(False)
                            return
                        alvo = entradas[0].get("url")

                opcoes_info = {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                    "playlistend": 1,
                }
                with yt_dlp.YoutubeDL(opcoes_info) as ydl_info:
                    info_playlist = ydl_info.extract_info(alvo, download=False)
                    titulo_bruto = (info_playlist or {}).get("title") or "Playlist"

                nome_pasta_playlist = yt_dlp.utils.sanitize_filename(titulo_bruto).strip() or "Playlist"
                destino_playlist = os.path.join(destino, nome_pasta_playlist)
                os.makedirs(destino_playlist, exist_ok=True)

                opcoes_playlist = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(destino_playlist, "%(playlist_index)s - %(title)s.%(ext)s"),
                    "noplaylist": False,
                    "ignoreerrors": True,
                    "quiet": True,
                    "no_warnings": True,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        },
                    ],
                }
                self.sinal_status.emit(f"Baixando: {nome_pasta_playlist[:22]}...")
                with yt_dlp.YoutubeDL(opcoes_playlist) as ydl_playlist:
                    ydl_playlist.download([alvo])

            self.sinal_status.emit("Download concluído!")
            self.sinal_concluido.emit(True)

        except Exception as erro:
            self.sinal_status.emit(f"Erro: {str(erro)[:40]}")
            self.sinal_concluido.emit(False)

    def atualizar_status(self, mensagem):
        self.texto_status.setText(mensagem)

    def finalizar_download(self, sucesso):
        self.botao_download.setEnabled(True)
        if sucesso:
            self.link_escolhido = None
            self.ignorar_alteracao_texto = True
            self.barra_pesquisa.clear()
            self.ignorar_alteracao_texto = False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())