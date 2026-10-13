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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...calcul import coordonnee_liaison, refermer, regler_liaison, residu_de_fermeture
from ...i18n import tr, traducteur
from ...modele import Couple, Force, Ressort
from ...modele.liaisons import TYPES_LIAISON
from ...modele.lois import LOIS, TYPES_LOI, LoiMouvement, dimension_du_role
from ...physique.unites import LONGUEURS
from ..document import Document, Ref
from ..widgets.champs import ChampNombre, ChampTexte, ZoneTexte, formater


class PanneauProprietes(QWidget):
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
            cle += [objet.solide_a, objet.solide_b, m.moteur_de_liaison(ref.id) is not None]
        if ref is not None and ref.genre == "moteur":
            cle += [objet.loi.type, objet.liaison in m.liaisons]
        if ref is not None and ref.genre == "solide":
            cle += [bool(m.liaisons_du_solide(ref.id))]
        return tuple(cle)

    def _planifier(self) -> None:
        """Reconstruit au prochain tour de boucle.

        Le formulaire ne doit pas être détruit pendant qu'un de ses propres
        composants est en train d'émettre le signal qui a tout déclenché.
        """
        if not self._en_attente:
            self._en_attente = True
            QTimer.singleShot(0, self.reconstruire)

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
        with self.doc.modification(fusion):
            operation()

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

    def _rubrique(self, texte: str) -> None:
        etiquette = QLabel(texte)
        etiquette.setProperty("role", "rubrique")
        etiquette.setWordWrap(True)
        self._disposition.addWidget(etiquette)
        self._formulaire = None

    def _ligne(self, libelle: str, composant: QWidget) -> None:
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
        self._formulaire.addRow(etiquette, composant)

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
    ) -> ChampNombre:
        champ = ChampNombre(dimension, self._unites, expression, minimum, strict)
        symbole = champ.symbole()
        self._ligne(f"{libelle} ({symbole})" if symbole else libelle, champ)
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

    def _choix(self, libelle: str, options, lire: Callable[[], str], ecrire: Callable[[str], None]) -> QComboBox:
        """Liste déroulante ; ``options`` est une suite de (valeur, texte affiché)."""
        liste = QComboBox()
        for valeur, texte in options:
            liste.addItem(texte, valeur)
        self._ligne(libelle, liste)
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

    def _lecture(self, libelle: str, lire: Callable[[], str]) -> QLabel:
        valeur = QLabel()
        valeur.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._ligne(libelle, valeur)

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

        self._rubrique(tr("proprietes.inertie"))
        self._nombre(tr("champ.masse"), "masse", lambda: s().inertie.masse, lambda v: setattr(s().inertie, "masse", v), minimum=0.0)
        self._nombre(tr("champ.gx"), "longueur", lambda: s().inertie.gx, lambda v: setattr(s().inertie, "gx", v))
        self._nombre(tr("champ.gy"), "longueur", lambda: s().inertie.gy, lambda v: setattr(s().inertie, "gy", v))
        self._nombre(tr("champ.jz"), "inertie", lambda: s().inertie.jz, lambda v: setattr(s().inertie, "jz", v), minimum=0.0)

        def repartir() -> None:
            self._modifier(lambda: setattr(s(), "inertie", s().inertie_barres_homogenes(s().inertie.masse)))

        self._bouton(tr("proprietes.barres"), repartir).setToolTip(tr("proprietes.barres_aide"))

        libre = not doc.mecanisme.liaisons_du_solide(ref.id)
        self._rubrique(tr("proprietes.pose"))
        self._nombre(tr("champ.x"), "longueur", lambda: s().pose.x, (lambda v: setattr(s().pose, "x", v)) if libre else None)
        self._nombre(tr("champ.y"), "longueur", lambda: s().pose.y, (lambda v: setattr(s().pose, "y", v)) if libre else None)
        self._nombre(tr("champ.angle"), "angle", lambda: s().pose.angle, (lambda v: setattr(s().pose, "angle", v)) if libre else None)
        if not libre:
            self._note(tr("proprietes.pose_note"))

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
        self._choix(
            tr("champ.type"),
            [(t, tr(f"liaison.type.{t}")) for t in TYPES_LIAISON],
            lambda: l().type,
            lambda v: m().changer_type_liaison(ref.id, v),
        )
        self._choix(
            tr("champ.modele_spatial"),
            [(cle, tr(f"spatial.{cle}")) for cle in liaison.MODELES_SPATIAUX],
            lambda: l().modele_spatial,
            lambda v: setattr(l(), "modele_spatial", v),
        ).setToolTip(tr("proprietes.liaison.modele_aide"))
        self._lecture(tr("proprietes.liaison.mobilites"), lambda: ", ".join(l().composantes_cinematiques()) or tr("proprietes.liaison.aucune"))
        self._lecture(tr("proprietes.liaison.inconnues"), lambda: ", ".join(l().composantes_statiques()))

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
            self._rubrique(tr("proprietes.liaison.torseur", a=a.nom, b=b.nom))

            def composante(grandeur: str, dimension: str) -> str:
                """Valeur affichée ; le bruit d'arrondi (10⁻⁹ de l'effort transmis) est ramené à zéro."""
                valeur = doc.resultats.valeur(f"liaison/{ref.id}/{grandeur}", doc.indice)
                norme = doc.resultats.valeur(f"liaison/{ref.id}/R", doc.indice)
                echelle = norme * (m().longueur_caracteristique() if dimension == "moment" else 1.0)
                return unites.formater(0.0 if abs(valeur) <= 1e-9 * echelle else valeur, dimension)

            for grandeur, dimension in (("X", "force"), ("Y", "force"), ("N", "moment"), ("R", "force")):
                self._lecture(tr(f"grandeur.{grandeur}"), lambda g=grandeur, d=dimension: composante(g, d))

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
            self._rubrique(tr("proprietes.action.composantes"))
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
            self._nombre(tr("champ.mz"), "moment", lambda: a().mz, lambda v: setattr(a(), "mz", v), expression=True)
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

        self._rubrique(tr("proprietes.moteur.loi"))

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
            )
            self._lecture(tr("grandeur.puissance"), lambda: unites.formater(doc.resultats.valeur(f"moteur/{ref.id}/puissance", doc.indice), "puissance"))
