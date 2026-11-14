"""Panneau des propriétés de l'objet sélectionné.

Le formulaire est reconstruit quand la sélection (ou sa structure) change, et
simplement rafraîchi quand seules des valeurs changent : on ne perd donc pas
le curseur en cours de saisie. Les champs relisent toujours l'objet à partir
du document, jamais par une référence gardée, pour rester justes après une
annulation.
"""

from __future__ import annotations

import math
from typing import Any, Callable, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...calcul import coordonnee_liaison, refermer, regler_liaison, residu_de_fermeture
from ...i18n import tr, traducteur
from ...modele import Couple, Force, Ressort
from ...modele.contacts import pas as pas_denture
from ...modele.liaisons import NATURES_CAME, NATURES_ENGRENAGE, TYPES_POINT, Came, Engrenage, Pivot
from ...modele.lois import LOIS, TYPES_LOI, LoiMouvement, dimension_du_role
from ...physique.unites import LONGUEURS
from ..aide import bouton_aide
from ..document import Document, Ref
from ..icones import icone
from ..widgets.champs import ChampNombre, ChampTexte, ZoneTexte, formater

Aide = Optional[tuple]
"""(fiche de cours, section) du bouton « ? » d'une ligne du formulaire."""


class PanneauProprietes(QWidget):
    outil_demande = Signal(str)
    """Demande d'activation d'un outil de la vue (étalonnage, déplacement de la photo)."""
    detection_demandee = Signal()
    """Demande d'ouverture de la détection des formes sur la photo de fond."""

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self._liens: List[Callable[[], None]] = []
        self._cle: Any = None
        self._formulaire: Optional[QFormLayout] = None

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        self._zone = QScrollArea()
        self._zone.setWidgetResizable(True)
        self._zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        racine.addWidget(self._zone)

        self._en_attente = False
        document.selection_change.connect(self._planifier)
        document.modele_change.connect(self._sur_modele)
        document.resultats_change.connect(self._sur_modele)
        document.temps_change.connect(lambda _: self.actualiser())
        traducteur.abonner(self._planifier)
        self.reconstruire()

    # ------------------------------------------------------------- mécanique
    def _unites(self):
        return self.doc.mecanisme.unites

    def _structure(self) -> Any:
        """Ce qui, en changeant, impose de reconstruire le formulaire."""
        doc = self.doc
        ref = doc.selection
        objet = doc.objet(ref)
        if objet is None:
            ref = None  # sélection devenue caduque (objet supprimé, annulation) : panneau du projet
        m = doc.mecanisme
        cle: List[Any] = [ref, type(objet).__name__, m.unites.longueur, m.unites.angle, doc.resultats is not None]
        if ref is not None and ref.genre == "liaison":
            cle += [objet.solide_a, objet.solide_b, m.moteur_de_liaison(ref.id) is not None, getattr(objet, "nature", "")]
        if ref is not None and ref.genre == "moteur":
            cle += [objet.loi.type, objet.liaison in m.liaisons]
        if ref is not None and ref.genre == "solide":
            cle += [bool(m.liaisons_du_solide(ref.id)), tuple(objet.cercles)]
        return tuple(cle)

    def _planifier(self) -> None:
        """Reconstruit au prochain tour de boucle.

        Le formulaire ne doit pas être détruit pendant qu'un de ses propres
        composants est en train d'émettre le signal qui a tout déclenché.
        """
        if not self._en_attente:
            self._en_attente = True
            QTimer.singleShot(0, self, self.reconstruire)  # annulé si le panneau est détruit entre-temps

    def _sur_modele(self) -> None:
        if self._en_attente:
            return
        if self._structure() != self._cle:
            self._planifier()
        else:
            self.actualiser()

    def actualiser(self) -> None:
        if self._en_attente:
            return
        for lien in self._liens:
            lien()

    def _modifier(self, operation: Callable[[], None], fusion: str = "") -> None:
        """Applique une modification ; si elle est refusée (valeur impossible), le modèle reste inchangé."""
        try:
            with self.doc.modification(fusion):
                operation()
        except ValueError:
            fenetre = self.window()
            if hasattr(fenetre, "statusBar"):
                fenetre.statusBar().showMessage(tr("proprietes.modification_refusee"), 6000)
            self.actualiser()

    # ------------------------------------------------------------ construction
    def reconstruire(self) -> None:
        self._en_attente = False
        self._liens = []
        conteneur = QWidget()
        disposition = QVBoxLayout(conteneur)
        disposition.setContentsMargins(12, 10, 12, 12)
        disposition.setSpacing(6)
        self._disposition = disposition
        self._formulaire = None

        ref = self.doc.selection
        objet = self.doc.objet(ref)
        if objet is None:
            self._projet()
        elif ref.genre == "solide":
            self._solide(ref)
        elif ref.genre == "point":
            self._point(ref)
        elif ref.genre == "liaison":
            self._liaison(ref)
        elif ref.genre == "action":
            self._action(ref)
        elif ref.genre == "moteur":
            self._moteur(ref)
        elif ref.genre == "fond":
            self._fond()
        disposition.addStretch(1)
        self._zone.setWidget(conteneur)
        self._cle = self._structure()
        self.actualiser()

    def _titre(self, texte: str, sous_titre: str = "") -> None:
        titre = QLabel(texte)
        titre.setProperty("role", "titre")
        titre.setWordWrap(True)
        self._disposition.addWidget(titre)
        if sous_titre:
            secondaire = QLabel(sous_titre)
            secondaire.setProperty("role", "secondaire")
            secondaire.setWordWrap(True)
            self._disposition.addWidget(secondaire)
        self._formulaire = None

    def _rubrique(self, texte: str, aide: Aide = None) -> None:
        etiquette = QLabel(texte)
        etiquette.setProperty("role", "rubrique")
        etiquette.setWordWrap(True)
        if aide is None:
            self._disposition.addWidget(etiquette)
        else:
            rangee = QHBoxLayout()
            rangee.setContentsMargins(0, 0, 0, 0)
            rangee.addWidget(etiquette, 1)
            rangee.addWidget(bouton_aide(*aide), 0, Qt.AlignBottom)
            self._disposition.addLayout(rangee)
        self._formulaire = None

    def _ligne(self, libelle: str, composant: QWidget, aide: Aide = None) -> None:
        if self._formulaire is None:
            self._formulaire = QFormLayout()
            self._formulaire.setContentsMargins(0, 0, 0, 0)
            self._formulaire.setHorizontalSpacing(10)
            self._formulaire.setVerticalSpacing(6)
            self._formulaire.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            self._formulaire.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._disposition.addLayout(self._formulaire)
        etiquette = QLabel(libelle)
        etiquette.setProperty("role", "secondaire")
        # un libellé long passe à la ligne au lieu de pousser le champ hors du panneau
        etiquette.setWordWrap(True)
        etiquette.setMinimumWidth(96)
        etiquette.setMaximumWidth(150)
        composant.setMinimumWidth(90)
        if aide is None:
            self._formulaire.addRow(etiquette, composant)
            return
        rangee = QWidget()
        boite = QHBoxLayout(rangee)
        boite.setContentsMargins(0, 0, 0, 0)
        boite.setSpacing(2)
        boite.addWidget(composant, 1)
        boite.addWidget(bouton_aide(*aide))
        self._formulaire.addRow(etiquette, rangee)

    def _note(self, texte: str) -> QLabel:
        note = QLabel(texte)
        note.setProperty("role", "secondaire")
        note.setWordWrap(True)
        self._disposition.addWidget(note)
        self._formulaire = None
        return note

    def _bouton(self, texte: str, action: Callable[[], None]) -> QPushButton:
        bouton = QPushButton(texte)
        bouton.clicked.connect(lambda: action())
        self._disposition.addWidget(bouton)
        self._formulaire = None
        return bouton

    def _nombre(
        self,
        libelle: str,
        dimension: str,
        lire: Callable[[], Any],
        ecrire: Optional[Callable[[Any], None]],
        expression: bool = False,
        minimum: Optional[float] = None,
        strict: bool = False,
        modification: bool = True,
        aide: Aide = None,
    ) -> ChampNombre:
        champ = ChampNombre(dimension, self._unites, expression, minimum, strict)
        symbole = champ.symbole()
        self._ligne(f"{libelle} ({symbole})" if symbole else libelle, champ, aide)
        if ecrire is None:
            champ.setReadOnly(True)
        elif modification:
            champ.modifie.connect(lambda v: self._modifier(lambda: ecrire(v)))
        else:
            champ.modifie.connect(lambda v: ecrire(v))

        def rafraichir() -> None:
            if champ.hasFocus() and champ.isModified():
                return
            try:
                champ.definir(lire())
            except (KeyError, AttributeError, ValueError):
                pass

        self._liens.append(rafraichir)
        return champ

    def _texte(self, libelle: str, lire: Callable[[], str], ecrire: Callable[[str], None]) -> ChampTexte:
        champ = ChampTexte()
        self._ligne(libelle, champ)
        champ.modifie.connect(lambda v: self._modifier(lambda: ecrire(v)))

        def rafraichir() -> None:
            if not (champ.hasFocus() and champ.isModified()):
                try:
                    champ.definir(lire())
                except (KeyError, AttributeError):
                    pass

        self._liens.append(rafraichir)
        return champ

    def _case(self, libelle: str, lire: Callable[[], bool], ecrire: Callable[[bool], None]) -> QCheckBox:
        case = QCheckBox(libelle)
        self._disposition.addWidget(case)
        self._formulaire = None
        case.clicked.connect(lambda etat: self._modifier(lambda: ecrire(bool(etat))))

        def rafraichir() -> None:
            try:
                valeur = bool(lire())
            except (KeyError, AttributeError):
                return
            if case.isChecked() != valeur:
                case.setChecked(valeur)

        self._liens.append(rafraichir)
        return case

    def _choix(self, libelle: str, options, lire: Callable[[], str], ecrire: Callable[[str], None], aide: Aide = None) -> QComboBox:
        """Liste déroulante ; ``options`` est une suite de (valeur, texte affiché)."""
        liste = QComboBox()
        for valeur, texte in options:
            liste.addItem(texte, valeur)
        self._ligne(libelle, liste, aide)
        liste.activated.connect(lambda _: self._modifier(lambda: ecrire(liste.currentData())))

        def rafraichir() -> None:
            try:
                indice = liste.findData(lire())
            except (KeyError, AttributeError):
                return
            if indice >= 0 and indice != liste.currentIndex():
                liste.setCurrentIndex(indice)

        self._liens.append(rafraichir)
        return liste

    def _lecture(self, libelle: str, lire: Callable[[], str], aide: Aide = None) -> QLabel:
        valeur = QLabel()
        valeur.setTextInteractionFlags(Qt.TextSelectableByMouse)
        valeur.setWordWrap(True)
        self._ligne(libelle, valeur, aide)

        def rafraichir() -> None:
            try:
                valeur.setText(lire())
            except (KeyError, AttributeError, ValueError):
                valeur.setText("—")

        self._liens.append(rafraichir)
        return valeur

    # ------------------------------------------------------------------ projet
    def _projet(self) -> None:
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731 - toujours le modèle courant
        self._titre(tr("proprietes.projet.titre"), tr("proprietes.projet.aide"))
        self._texte(tr("proprietes.projet.nom"), lambda: m().titre, lambda v: setattr(m(), "titre", v))
        self._texte(tr("proprietes.projet.auteur"), lambda: m().auteur, lambda v: setattr(m(), "auteur", v))
        description = ZoneTexte()
        description.setPlaceholderText(tr("proprietes.projet.description"))
        description.setFixedHeight(70)
        self._disposition.addWidget(description)
        self._formulaire = None
        description.modifie.connect(lambda texte: self._modifier(lambda: setattr(m(), "description", texte)))
        self._liens.append(lambda: None if description.hasFocus() else description.definir(m().description))

        self._rubrique(tr("proprietes.unites"))

        def changer_unite(attribut: str, valeur: str) -> None:
            setattr(m().unites, attribut, valeur)

        self._choix(tr("proprietes.unite_longueur"), [(u, u) for u in LONGUEURS], lambda: m().unites.longueur, lambda v: changer_unite("longueur", v))
        self._choix(
            tr("proprietes.unite_angle"),
            [("deg", tr("unite.degre")), ("rad", tr("unite.radian"))],
            lambda: m().unites.angle,
            lambda v: changer_unite("angle", v),
        )
        self._rubrique(tr("proprietes.affichage"))
        self._nombre(tr("proprietes.pas_grille"), "longueur", lambda: m().affichage["pas_grille"], lambda v: m().affichage.__setitem__("pas_grille", v), minimum=0.0, strict=True)
        for cle in ("grille", "aimantation", "noms_points", "noms_liaisons", "centres_gravite"):
            self._case(tr(f"affichage.{cle}"), lambda c=cle: m().affichage.get(c, True), lambda v, c=cle: m().affichage.__setitem__(c, v))

    # ------------------------------------------------------------------ solide
    def _solide(self, ref: Ref) -> None:
        doc = self.doc
        s = lambda: doc.mecanisme.solides[ref.id]  # noqa: E731
        solide = s()
        self._titre(solide.nom, tr("proprietes.solide.bati") if solide.bati else tr("proprietes.solide.mobile"))
        self._texte(tr("champ.nom"), lambda: s().nom, lambda v: setattr(s(), "nom", v or s().nom))

        couleur = QPushButton()
        couleur.setFixedHeight(26)
        self._ligne(tr("champ.couleur"), couleur)

        def choisir_couleur() -> None:
            choisie = QColorDialog.getColor(QColor(s().couleur), self, tr("champ.couleur"))
            if choisie.isValid():
                self._modifier(lambda: setattr(s(), "couleur", choisie.name().upper()))

        couleur.clicked.connect(choisir_couleur)
        self._liens.append(lambda: couleur.setStyleSheet(f"background: {s().couleur}; border: 1px solid rgba(128,128,128,0.5);"))

        if solide.bati:
            self._note(tr("proprietes.solide.note_bati"))
            return

        self._rubrique(tr("proprietes.inertie"), ("inertie", "rubrique"))
        self._nombre(tr("champ.masse"), "masse", lambda: s().inertie.masse, lambda v: setattr(s().inertie, "masse", v), minimum=0.0, aide=("centre_gravite", "masse"))
        self._nombre(tr("champ.gx"), "longueur", lambda: s().inertie.gx, lambda v: setattr(s().inertie, "gx", v), aide=("centre_gravite", "position"))
        self._nombre(tr("champ.gy"), "longueur", lambda: s().inertie.gy, lambda v: setattr(s().inertie, "gy", v), aide=("centre_gravite", "position"))
        self._nombre(tr("champ.jz"), "inertie", lambda: s().inertie.jz, lambda v: setattr(s().inertie, "jz", v), minimum=0.0, aide=("inertie", "jz"))

        def repartir() -> None:
            self._modifier(lambda: setattr(s(), "inertie", s().inertie_barres_homogenes(s().inertie.masse)))

        if solide.segments:
            self._bouton(tr("proprietes.barres"), repartir).setToolTip(tr("proprietes.barres_aide"))
        if solide.cercles:

            def disque() -> None:
                self._modifier(lambda: setattr(s(), "inertie", s().inertie_disque_homogene(s().inertie.masse)))

            self._bouton(tr("proprietes.disque"), disque).setToolTip(tr("proprietes.disque_aide"))
            self._cercles_du_solide(ref)

        libre = not doc.mecanisme.liaisons_du_solide(ref.id)
        self._rubrique(tr("proprietes.pose"))
        self._nombre(tr("champ.x"), "longueur", lambda: s().pose.x, (lambda v: setattr(s().pose, "x", v)) if libre else None)
        self._nombre(tr("champ.y"), "longueur", lambda: s().pose.y, (lambda v: setattr(s().pose, "y", v)) if libre else None)
        self._nombre(tr("champ.angle"), "angle", lambda: s().pose.angle, (lambda v: setattr(s().pose, "angle", v)) if libre else None)
        if not libre:
            self._note(tr("proprietes.pose_note"))

    def _cercles_du_solide(self, ref: Ref) -> None:
        """Rayon de chaque cercle du solide, son excentricité par rapport à l'articulation, et sa suppression."""
        doc = self.doc
        s = lambda: doc.mecanisme.solides[ref.id]  # noqa: E731
        self._rubrique(tr("proprietes.cercles"), ("excentricite", "cercle"))
        for cercle_id in list(s().cercles):
            c = lambda cid=cercle_id: s().cercles[cid]  # noqa: E731
            centre = s().points[c().centre].nom if c().centre in s().points else "?"
            self._nombre(
                tr("proprietes.cercle.rayon", centre=centre),
                "longueur",
                lambda c=c: c().rayon,
                lambda v, c=c: setattr(c(), "rayon", v) if v > 0.0 else None,
                minimum=0.0,
                strict=True,
            )

            def excentricite(c=c) -> str:
                articulation = doc.mecanisme.centre_de_rotation(ref.id)
                if articulation is None:
                    return "—"
                centre = s().points[c().centre]
                return self._unites().formater(math.hypot(centre.x - articulation.x, centre.y - articulation.y), "longueur")

            self._lecture(tr("proprietes.cercle.excentricite"), excentricite, ("excentricite", "excentricite"))
            supprimer = self._bouton(tr("proprietes.cercle.supprimer", centre=centre), lambda cid=cercle_id: self._modifier(lambda: doc.mecanisme.supprimer_cercle(ref.id, cid)))
            supprimer.setIcon(icone("supprimer", taille=16))

    # ------------------------------------------------------------------- point
    def _point(self, ref: Ref) -> None:
        doc = self.doc
        s = lambda: doc.mecanisme.solides[ref.id]  # noqa: E731
        point = lambda: s().points[ref.sous]  # noqa: E731
        self._titre(tr("proprietes.point.titre", nom=point().nom), tr("proprietes.point.de", solide=s().nom))
        self._texte(tr("champ.nom"), lambda: point().nom, lambda v: setattr(point(), "nom", v or point().nom))

        def placer(x: Optional[float] = None, y: Optional[float] = None) -> None:
            gx, gy = s().position_globale(ref.sous)
            s().placer_point_global(ref.sous, gx if x is None else x, gy if y is None else y)
            m = doc.mecanisme
            if residu_de_fermeture(m) > 1e-9 * m.longueur_caracteristique():
                refermer(m)

        self._rubrique(tr("proprietes.point.position"))
        self._nombre(tr("champ.x"), "longueur", lambda: s().position_globale(ref.sous)[0], lambda v: placer(x=v))
        self._nombre(tr("champ.y"), "longueur", lambda: s().position_globale(ref.sous)[1], lambda v: placer(y=v))
        self._note(tr("proprietes.point.note"))
        if doc.resultats is not None:
            self._resultats_point(ref)

    def _resultats_point(self, ref: Ref) -> None:
        doc = self.doc
        base = f"point/{ref.id}/{ref.sous}/"
        if base + "v" not in doc.resultats.canaux:
            return
        unites = self._unites()
        self._rubrique(tr("proprietes.resultats"))
        for grandeur, dimension in (("v", "vitesse"), ("a", "acceleration")):
            self._lecture(
                tr(f"grandeur.{grandeur}"),
                lambda g=grandeur, d=dimension: unites.formater(doc.resultats.valeur(base + g, doc.indice), d),
            )

    # ----------------------------------------------------------------- liaison
    def _liaison(self, ref: Ref) -> None:
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731
        l = lambda: doc.mecanisme.liaisons[ref.id]  # noqa: E731,E741
        liaison = l()
        a, b = m().solides[liaison.solide_a], m().solides[liaison.solide_b]
        self._titre(liaison.nom, tr("proprietes.liaison.entre", a=a.nom, b=b.nom))
        self._texte(tr("champ.nom"), lambda: l().nom, lambda v: setattr(l(), "nom", v or l().nom))
        if liaison.CONTACT:
            self._lecture(tr("champ.type"), lambda: tr(f"liaison.type.{l().type}"), ("ddl", "type"))
        else:
            self._choix(
                tr("champ.type"),
                [(t, tr(f"liaison.type.{t}")) for t in TYPES_POINT],
                lambda: l().type,
                lambda v: m().changer_type_liaison(ref.id, v),
                ("ddl", "type"),
            )
        self._choix(
            tr("champ.modele_spatial"),
            [(cle, tr(f"spatial.{cle}")) for cle in liaison.MODELES_SPATIAUX],
            lambda: l().modele_spatial,
            lambda v: setattr(l(), "modele_spatial", v),
            ("isostatisme", "modele_spatial"),
        ).setToolTip(tr("proprietes.liaison.modele_aide"))
        self._lecture(tr("proprietes.liaison.mobilites"), lambda: ", ".join(l().composantes_cinematiques()) or tr("proprietes.liaison.aucune"), ("ddl", "mobilites"))
        self._lecture(tr("proprietes.liaison.inconnues"), lambda: ", ".join(l().composantes_statiques()), ("torseur", "inconnues"))
        if isinstance(liaison, Engrenage):
            self._engrenage(ref)
        elif isinstance(liaison, Came):
            self._came(ref)

        if liaison.A_UN_AXE:
            self._rubrique(tr("proprietes.liaison.axe"))

            def orienter(angle_global: float) -> None:
                l().angle_axe = angle_global - m().solides[l().solide_a].pose.angle
                if residu_de_fermeture(m()) > 1e-9 * m().longueur_caracteristique():
                    refermer(m())

            self._nombre(tr("champ.direction_axe"), "angle", lambda: m().angle_axe_global(l()), orienter)
            self._bouton(tr("proprietes.liaison.inverser"), lambda: self._modifier(lambda: m().inverser_liaison(ref.id))).setToolTip(
                tr("proprietes.liaison.inverser_aide", a=a.nom)
            )

        if liaison.PILOTAGE is not None:
            rotation = liaison.PILOTAGE == "rotation"
            self._rubrique(tr("proprietes.liaison.position"))

            def regler(valeur: float) -> None:
                if not regler_liaison(m(), ref.id, valeur):
                    self.window().statusBar().showMessage(tr("proprietes.liaison.inaccessible"), 5000)

            self._nombre(
                tr("champ.angle_articulaire") if rotation else tr("champ.deplacement"),
                "angle" if rotation else "longueur",
                lambda: coordonnee_liaison(m(), ref.id),
                regler,
            ).setToolTip(tr("proprietes.liaison.position_aide"))

            self._rubrique(tr("proprietes.liaison.dynamique"))
            self._nombre(
                tr("champ.amortissement"),
                "amortissement_angulaire" if rotation else "amortissement",
                lambda: l().amortissement,
                lambda v: setattr(l(), "amortissement", v),
                minimum=0.0,
            )
            self._nombre(
                tr("champ.vitesse_initiale"),
                "vitesse_angulaire" if rotation else "vitesse",
                lambda: l().vitesse_initiale,
                lambda v: setattr(l(), "vitesse_initiale", v),
            )
            moteur = m().moteur_de_liaison(ref.id)
            if moteur is None:

                def motoriser() -> None:
                    with doc.modification():
                        nouveau = m().creer_moteur(ref.id)
                    doc.selectionner(Ref("moteur", nouveau.id))

                self._bouton(tr("proprietes.liaison.motoriser"), motoriser)
            else:
                self._bouton(tr("proprietes.liaison.voir_moteur", nom=moteur.nom), lambda: doc.selectionner(Ref("moteur", moteur.id)))

        if doc.resultats is not None and f"liaison/{ref.id}/X" in doc.resultats.canaux:
            unites = self._unites()
            self._rubrique(tr("proprietes.liaison.torseur", a=a.nom, b=b.nom), ("torseur", "liaison"))

            def composante(grandeur: str, dimension: str) -> str:
                """Valeur affichée ; le bruit d'arrondi (10⁻⁹ de l'effort transmis) est ramené à zéro."""
                valeur = doc.resultats.valeur(f"liaison/{ref.id}/{grandeur}", doc.indice)
                norme = doc.resultats.valeur(f"liaison/{ref.id}/R", doc.indice)
                echelle = norme * (m().longueur_caracteristique() if dimension == "moment" else 1.0)
                return unites.formater(0.0 if abs(valeur) <= 1e-9 * echelle else valeur, dimension)

            for grandeur, dimension in (("X", "force"), ("Y", "force"), ("N", "moment"), ("R", "force")):
                self._lecture(tr(f"grandeur.{grandeur}"), lambda g=grandeur, d=dimension: composante(g, d))
            for grandeur, dimension, aide in (
                ("Ft", "force", ("engrenages", "efforts")),
                ("Fr", "force", ("engrenages", "efforts")),
                ("Fn", "force", ("excentricite", "effort_normal") if isinstance(liaison, Came) else ("engrenages", "efforts")),
                ("couple_a", "moment", ("engrenages", "couples")),
                ("couple_b", "moment", ("engrenages", "couples")),
            ):
                if liaison.CONTACT and f"liaison/{ref.id}/{grandeur}" in doc.resultats.canaux:
                    self._lecture(
                        tr(f"grandeur.{grandeur}"),
                        lambda g=grandeur, d=dimension: unites.formater(doc.resultats.valeur(f"liaison/{ref.id}/{g}", doc.indice), d),
                        aide,
                    )

    # --------------------------------------------------------------- engrenage
    def _engrenage(self, ref: Ref) -> None:
        """Paramètres d'un engrenage et grandeurs qui s'en déduisent (diamètres, entraxe, rapport)."""
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731
        l = lambda: doc.mecanisme.liaisons[ref.id]  # noqa: E731,E741
        unites = self._unites()
        cremaillere = l().cremaillere
        self._rubrique(tr("proprietes.engrenage.titre"), ("engrenages", "rubrique"))

        def changer_nature(nature: str) -> None:
            if nature == "cremaillere" or l().cremaillere:
                raise ValueError("crémaillère")  # la géométrie change trop : recréer l'engrenage
            l().nature = nature

        self._choix(
            tr("champ.nature"),
            [(n, tr(f"engrenage.nature.{n}")) for n in NATURES_ENGRENAGE if (n == "cremaillere") == cremaillere],
            lambda: l().nature,
            changer_nature,
            ("engrenages", "nature"),
        )

        def dents(attribut: str, valeur: float) -> None:
            if valeur >= 1.0 and float(valeur).is_integer():
                self._suivre_cercles(attribut, l().module, valeur)
                setattr(l(), attribut, float(valeur))

        def module(valeur: float) -> None:
            if valeur > 0.0:
                self._suivre_cercles("z_a", valeur, l().z_a)
                if not l().cremaillere:
                    self._suivre_cercles("z_b", valeur, l().z_b)
                l().module = valeur

        self._nombre(tr("champ.z_a"), "sans", lambda: l().z_a, lambda v: dents("z_a", v), minimum=1.0, aide=("engrenages", "dents"))
        if not cremaillere:
            self._nombre(tr("champ.z_b"), "sans", lambda: l().z_b, lambda v: dents("z_b", v), minimum=1.0, aide=("engrenages", "dents"))
        self._nombre(tr("champ.module"), "longueur", lambda: l().module, module, minimum=0.0, strict=True, aide=("engrenages", "module"))
        self._nombre(
            tr("champ.angle_pression"),
            "angle",
            lambda: l().angle_pression,
            lambda v: setattr(l(), "angle_pression", v) if 0.0 <= v <= math.radians(45.0) else None,
            minimum=0.0,
            aide=("engrenages", "angle_pression"),
        )
        self._nombre(
            tr("champ.rendement"),
            "sans",
            lambda: l().rendement,
            lambda v: setattr(l(), "rendement", v) if 0.0 < v <= 1.0 else None,
            minimum=0.0,
            strict=True,
            aide=("engrenages", "rendement"),
        )
        if cremaillere:
            self._nombre(
                tr("champ.direction_cremaillere"),
                "angle",
                lambda: m().solides[l().solide_b].pose.angle + l().angle_axe,
                lambda v: setattr(l(), "angle_axe", v - m().solides[l().solide_b].pose.angle),
            )

        self._rubrique(tr("proprietes.engrenage.calculs"), ("engrenages", "formules"))
        self._lecture(tr("proprietes.engrenage.diametre_a"), lambda: unites.formater(l().module * l().z_a, "longueur"), ("engrenages", "diametre"))
        if not cremaillere:
            self._lecture(tr("proprietes.engrenage.diametre_b"), lambda: unites.formater(l().module * l().z_b, "longueur"), ("engrenages", "diametre"))
        self._lecture(tr("proprietes.engrenage.pas"), lambda: unites.formater(pas_denture(l().module), "longueur"), ("engrenages", "pas"))
        self._lecture(tr("proprietes.engrenage.entraxe_theorique"), lambda: unites.formater(l().entraxe_theorique(), "longueur"), ("engrenages", "entraxe"))
        self._lecture(tr("proprietes.engrenage.entraxe_reel"), lambda: unites.formater(self._entraxe_reel(ref), "longueur"))
        self._lecture(tr("proprietes.engrenage.rapport"), lambda: self._texte_rapport(l()), ("engrenages", "rapport"))
        ecart = abs(self._entraxe_reel(ref) - l().entraxe_theorique())
        if ecart > 1e-6 * max(l().entraxe_theorique(), 1e-9):
            self._note(tr("proprietes.engrenage.entraxe_different"))
            self._bouton(tr("proprietes.engrenage.ajuster"), lambda: self._ajuster_entraxe(ref)).setToolTip(tr("proprietes.engrenage.ajuster_aide"))

    def _suivre_cercles(self, attribut: str, module: float, z: float) -> None:
        """Le cercle primitif d'une roue suit son nombre de dents et le module de l'engrenage."""
        liaison = self.doc.mecanisme.liaisons[self.doc.selection.id]
        solide_id, point_id = (liaison.solide_a, liaison.point_a) if attribut == "z_a" else (liaison.solide_b, liaison.point_b)
        ancien = liaison.module * (liaison.z_a if attribut == "z_a" else liaison.z_b) / 2.0
        for cercle in self.doc.mecanisme.solides[solide_id].cercles.values():
            if cercle.centre == point_id and abs(cercle.rayon - ancien) <= 1e-9 * max(ancien, 1e-12):
                cercle.rayon = module * z / 2.0

    def _entraxe_reel(self, ref: Ref) -> float:
        m = self.doc.mecanisme
        liaison = m.liaisons[ref.id]
        oa = m.point_global(liaison.solide_a, liaison.point_a)
        if liaison.cremaillere:
            contact = m.contact(liaison)
            nx, ny = contact.glissement
            pb = m.point_global(liaison.solide_b, liaison.point_b)
            return abs(nx * (oa[0] - pb[0]) + ny * (oa[1] - pb[1]))
        ob = m.point_global(liaison.solide_b, liaison.point_b)
        return math.hypot(ob[0] - oa[0], ob[1] - oa[1])

    @staticmethod
    def _texte_rapport(liaison: Engrenage) -> str:
        if liaison.cremaillere:
            return tr("proprietes.engrenage.rapport_cremaillere", r=formater(liaison.rayon_primitif_a() * 1000.0))
        signe = "+" if liaison.nature == "interieur" else "−"
        return f"{signe}{liaison.z_a:g}/{liaison.z_b:g} = {formater(liaison.rapport())}"

    def _ajuster_entraxe(self, ref: Ref) -> None:
        """Rapproche ou éloigne la roue B (avec l'axe qui la porte) jusqu'à l'entraxe théorique."""
        doc = self.doc

        def operation() -> None:
            m = doc.mecanisme
            liaison = m.liaisons[ref.id]
            if liaison.cremaillere:
                raise ValueError("entraxe d'une crémaillère")
            oa = m.point_global(liaison.solide_a, liaison.point_a)
            ob = m.point_global(liaison.solide_b, liaison.point_b)
            reel = math.hypot(ob[0] - oa[0], ob[1] - oa[1])
            if reel <= 0.0:
                raise ValueError("centres confondus")
            facteur = liaison.entraxe_theorique() / reel
            cible = (oa[0] + (ob[0] - oa[0]) * facteur, oa[1] + (ob[1] - oa[1]) * facteur)
            dx, dy = cible[0] - ob[0], cible[1] - ob[1]
            roue = m.solides[liaison.solide_b]
            if roue.bati:
                raise ValueError("couronne liée au bâti")
            roue.pose.x += dx
            roue.pose.y += dy
            for pivot in [p for p in m.liaisons.values() if isinstance(p, Pivot) and p.concerne(roue.id)]:
                autre = pivot.autre_solide(roue.id)
                point = pivot.point_a if pivot.solide_a == autre else pivot.point_b
                x, y = m.point_global(autre, point)
                m.solides[autre].placer_point_global(point, x + dx, y + dy)
            if residu_de_fermeture(m) > 1e-9 * m.longueur_caracteristique() and not refermer(m):
                raise ValueError("fermeture impossible")

        try:
            with doc.modification():
                operation()
        except ValueError:
            self.window().statusBar().showMessage(tr("proprietes.engrenage.ajustement_impossible"), 6000)

    # -------------------------------------------------------------------- came
    def _came(self, ref: Ref) -> None:
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731
        l = lambda: doc.mecanisme.liaisons[ref.id]  # noqa: E731,E741
        unites = self._unites()

        def puis_refermer(ecrire: Callable[[Any], None]) -> Callable[[Any], None]:
            """Changer de poussoir ou de galet déplace le contact : le mécanisme est refermé."""

            def operation(valeur: Any) -> None:
                ecrire(valeur)
                if residu_de_fermeture(m()) > 1e-9 * m().longueur_caracteristique() and not refermer(m()):
                    raise ValueError("contact impossible")

            return operation

        self._rubrique(tr("proprietes.came.titre"), ("excentricite", "came"))
        self._choix(
            tr("champ.nature"),
            [(n, tr(f"came.nature.{n}")) for n in NATURES_CAME],
            lambda: l().nature,
            puis_refermer(lambda v: setattr(l(), "nature", v)),
            ("excentricite", "poussoirs"),
        )

        def cercle() -> str:
            c = m().solides[l().solide_a].cercles[l().cercle]
            return f"{m().solides[l().solide_a].nom} — R = {unites.formater(c.rayon, 'longueur')}"

        self._lecture(tr("champ.cercle"), cercle)
        if l().nature == "galet":
            self._nombre(
                tr("champ.rayon_galet"),
                "longueur",
                lambda: l().rayon_galet,
                puis_refermer(lambda v: setattr(l(), "rayon_galet", v)),
                minimum=0.0,
            )
        if l().nature == "plat":
            self._nombre(
                tr("champ.direction_plateau"),
                "angle",
                lambda: m().solides[l().solide_b].pose.angle + l().angle_axe,
                puis_refermer(lambda v: setattr(l(), "angle_axe", v - m().solides[l().solide_b].pose.angle)),
            )
        self._note(tr("proprietes.came.note"))

    # ------------------------------------------------------------------ action
    def _action(self, ref: Ref) -> None:
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731
        a = lambda: doc.mecanisme.actions[ref.id]  # noqa: E731
        action = a()
        self._titre(action.nom, tr(f"action.type.{action.type}"))
        self._texte(tr("champ.nom"), lambda: a().nom, lambda v: setattr(a(), "nom", v or a().nom))
        self._case(tr("champ.actif"), lambda: a().actif, lambda v: setattr(a(), "actif", v))

        if isinstance(action, Force):
            solide = m().solides[action.solide]
            self._lecture(tr("proprietes.action.applique_en"), lambda: f"{solide.points[a().point].nom} — {solide.nom}")
            self._rubrique(tr("proprietes.action.composantes"), ("moment", "force"))
            self._nombre(tr("champ.fx"), "force", lambda: a().fx, lambda v: setattr(a(), "fx", v), expression=True)
            self._nombre(tr("champ.fy"), "force", lambda: a().fy, lambda v: setattr(a(), "fy", v), expression=True)
            self._choix(
                tr("champ.repere"),
                [("global", tr("proprietes.action.repere_global")), ("local", tr("proprietes.action.repere_local"))],
                lambda: a().repere,
                lambda v: setattr(a(), "repere", v),
            )
            self._note(tr("proprietes.action.expression_aide"))
        elif isinstance(action, Couple):
            self._lecture(tr("proprietes.action.applique_a"), lambda: m().solides[a().solide].nom)
            self._nombre(tr("champ.mz"), "moment", lambda: a().mz, lambda v: setattr(a(), "mz", v), expression=True, aide=("couple_moteur", "couple"))
            self._note(tr("proprietes.action.expression_aide"))
        elif isinstance(action, Ressort):
            self._lecture(
                tr("proprietes.action.entre"),
                lambda: f"{m().solides[a().solide_a].nom} — {m().solides[a().solide_b].nom}",
            )
            self._nombre(tr("champ.raideur"), "raideur", lambda: a().raideur, lambda v: setattr(a(), "raideur", v), minimum=0.0)
            self._nombre(tr("champ.amortissement"), "amortissement", lambda: a().amortissement, lambda v: setattr(a(), "amortissement", v), minimum=0.0)
            self._nombre(tr("champ.longueur_libre"), "longueur", lambda: a().longueur_libre, lambda v: setattr(a(), "longueur_libre", v), minimum=0.0)

            def longueur() -> float:
                pa = m().point_global(a().solide_a, a().point_a)
                pb = m().point_global(a().solide_b, a().point_b)
                return math.hypot(pb[0] - pa[0], pb[1] - pa[1])

            self._nombre(tr("champ.longueur_actuelle"), "longueur", longueur, None)
            self._bouton(tr("proprietes.action.au_repos"), lambda: self._modifier(lambda: setattr(a(), "longueur_libre", longueur())))

    # -------------------------------------------------------------------- fond
    def _fond(self) -> None:
        """Photo de schéma : visibilité, transparence, position, échelle ; étalonnage et détection."""
        doc = self.doc
        f = lambda: doc.mecanisme.fond  # noqa: E731
        fond = f()
        self._titre(tr("proprietes.fond.titre"), fond.nom or tr("proprietes.fond.sans_nom"))
        self._case(tr("proprietes.fond.visible"), lambda: f().visible, lambda v: setattr(f(), "visible", v))

        curseur = QSlider(Qt.Horizontal)
        curseur.setRange(5, 100)
        self._ligne(tr("proprietes.fond.opacite"), curseur)
        curseur.valueChanged.connect(lambda v: self._modifier(lambda: setattr(f(), "opacite", v / 100.0), fusion="opacite"))
        curseur.sliderReleased.connect(doc.terminer_fusion)

        def rafraichir() -> None:
            if f() is not None and not curseur.isSliderDown():
                curseur.blockSignals(True)
                curseur.setValue(int(round(f().opacite * 100)))
                curseur.blockSignals(False)

        self._liens.append(rafraichir)
        self._rubrique(tr("proprietes.fond.placement"))
        self._nombre(tr("champ.x"), "longueur", lambda: f().x, lambda v: setattr(f(), "x", v))
        self._nombre(tr("champ.y"), "longueur", lambda: f().y, lambda v: setattr(f(), "y", v))
        self._nombre(tr("proprietes.fond.largeur"), "longueur", lambda: f().largeur, lambda v: setattr(f(), "largeur", v) if v > 0.0 else None, minimum=0.0, strict=True)
        self._nombre(tr("champ.angle"), "angle", lambda: f().angle, lambda v: setattr(f(), "angle", v))
        self._lecture(tr("proprietes.fond.taille"), lambda: f"{f().largeur_px} × {f().hauteur_px} px")
        self._note(tr("proprietes.fond.note"))
        self._bouton(tr("proprietes.fond.etalonner"), lambda: self.outil_demande.emit("etalonnage")).setIcon(icone("etalon", taille=16))
        self._bouton(tr("proprietes.fond.deplacer"), lambda: self.outil_demande.emit("photo")).setIcon(icone("deplacer", taille=16))
        self._bouton(tr("proprietes.fond.detecter"), self.detection_demandee.emit).setIcon(icone("detecter", taille=16))
        supprimer = self._bouton(tr("proprietes.fond.supprimer"), lambda: doc.supprimer(Ref("fond", "fond")))
        supprimer.setIcon(icone("supprimer", taille=16))

    # ------------------------------------------------------------------ moteur
    def _moteur(self, ref: Ref) -> None:
        doc = self.doc
        m = lambda: doc.mecanisme  # noqa: E731
        mo = lambda: doc.mecanisme.moteurs[ref.id]  # noqa: E731
        moteur = mo()
        liaison = m().liaisons.get(moteur.liaison)
        pilotage = (liaison.PILOTAGE if liaison is not None else None) or "rotation"
        self._titre(moteur.nom, tr("proprietes.moteur.sur", liaison=liaison.nom if liaison else "?"))
        self._texte(tr("champ.nom"), lambda: mo().nom, lambda v: setattr(mo(), "nom", v or mo().nom))
        self._case(tr("champ.actif"), lambda: mo().actif, lambda v: setattr(mo(), "actif", v))
        self._case(tr("proprietes.moteur.relatif"), lambda: mo().relatif, lambda v: setattr(mo(), "relatif", v)).setToolTip(
            tr("proprietes.moteur.relatif_aide")
        )
        if liaison is not None:
            self._bouton(tr("proprietes.moteur.voir_liaison", nom=liaison.nom), lambda: doc.selectionner(Ref("liaison", liaison.id)))

        self._rubrique(tr("proprietes.moteur.loi"), ("couple_moteur", "loi"))

        def changer_loi(type_loi: str) -> None:
            mo().loi = LoiMouvement(type_loi, dict(mo().loi.parametres))

        self._choix(tr("champ.type"), [(t, tr(f"loi.{t}")) for t in TYPES_LOI], lambda: mo().loi.type, changer_loi)
        self._note(tr(f"loi.aide.{moteur.loi.type}"))

        for nom, role, _ in LOIS[moteur.loi.type]:
            if role == "expression":
                champ = ChampTexte()
                self._ligne(tr("loi.param.expression"), champ)

                def ecrire_expression(texte: str, n: str = nom, c: ChampTexte = champ) -> None:
                    essai = LoiMouvement("expression", {n: texte})
                    try:
                        essai.verifier()
                    except ValueError as exc:
                        c.setProperty("invalide", True)
                        c.setToolTip(str(exc))
                        c.style().unpolish(c)
                        c.style().polish(c)
                        return
                    c.setProperty("invalide", False)
                    c.setToolTip("")
                    c.style().unpolish(c)
                    c.style().polish(c)
                    self._modifier(lambda: mo().loi.parametres.__setitem__(n, texte))

                champ.modifie.connect(ecrire_expression)
                self._liens.append(lambda c=champ, n=nom: None if (c.hasFocus() and c.isModified()) else c.definir(str(mo().loi.parametres[n])))
                self._note(tr("loi.aide.fonctions"))
            else:
                self._nombre(
                    tr(f"loi.param.{nom}"),
                    dimension_du_role(role, pilotage),
                    lambda n=nom: mo().loi.parametres[n],
                    lambda v, n=nom: mo().loi.parametres.__setitem__(n, v),
                )
        if moteur.loi.type == "vitesse_constante" and pilotage == "rotation":
            self._lecture(tr("proprietes.moteur.tours_minute"), lambda: formater(float(mo().loi.parametres["vitesse"]) * 30.0 / math.pi) + " tr/min")

        if doc.resultats is not None and f"moteur/{ref.id}/effort" in doc.resultats.canaux:
            unites = self._unites()
            self._rubrique(tr("proprietes.resultats"))
            self._lecture(
                tr("grandeur.effort_couple") if pilotage == "rotation" else tr("grandeur.effort_force"),
                lambda: unites.formater(doc.resultats.valeur(f"moteur/{ref.id}/effort", doc.indice), "moment" if pilotage == "rotation" else "force"),
                ("couple_moteur", "effort"),
            )
            self._lecture(tr("grandeur.puissance"), lambda: unites.formater(doc.resultats.valeur(f"moteur/{ref.id}/puissance", doc.indice), "puissance"))
