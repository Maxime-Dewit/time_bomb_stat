from datetime import timedelta

from django import forms
from django.db import transaction
from django.utils import timezone

from .models import Award, Game, Participation, Player, Role


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Nom du joueur", "autocomplete": "off", "class": "input"}
            )
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Player.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce joueur existe déjà.")
        return name


class NewGameForm(forms.Form):
    master = forms.ModelChoiceField(
        Player.objects.all(), required=False, empty_label="Pas de maître du jeu"
    )


class AddPlayersForm(forms.Form):
    players = forms.ModelMultipleChoiceField(Player.objects.all(), required=False)
    new_names = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(
            attrs={"placeholder": "Nouveaux joueurs (séparés par des virgules)"}
        ),
    )

    def clean_new_names(self):
        raw = self.cleaned_data["new_names"]
        names = [" ".join(n.split()) for n in raw.split(",")]
        return [n[:150] for n in names if n]

    def save(self, game: Game) -> int:
        players = list(self.cleaned_data["players"])
        for name in self.cleaned_data["new_names"]:
            existing = Player.objects.filter(name__iexact=name).first()
            players.append(existing or Player.objects.create(name=name))
        added = 0
        for player in players:
            _, created = Participation.objects.get_or_create(player=player, game=game)
            added += created
        return added


class GameResultForm(forms.Form):
    """Rôles et distinctions de chaque participant + camp gagnant + date."""

    SAVE, FINISH = "save", "finish"

    winner_role = forms.ChoiceField(
        label="Camp gagnant",
        choices=Role.choices,
        required=False,
        widget=forms.RadioSelect,
    )
    started_at = forms.DateTimeField(
        label="Début de la partie",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "input"}, format="%Y-%m-%dT%H:%M"
        ),
    )

    def __init__(self, *args, game: Game, **kwargs):
        self.game = game
        self.participations = list(game.participations.select_related("player"))
        initial = {
            "winner_role": game.winner_role,
            "started_at": timezone.localtime(game.started_at) if game.started_at else None,
        }
        for p in self.participations:
            initial[f"role_{p.player_id}"] = p.role
            initial[f"info_{p.player_id}"] = p.info
        super().__init__(*args, initial=initial, **kwargs)
        for p in self.participations:
            self.fields[f"role_{p.player_id}"] = forms.ChoiceField(
                choices=Role.choices, widget=forms.RadioSelect
            )
            self.fields[f"info_{p.player_id}"] = forms.ChoiceField(
                choices=Award.choices, widget=forms.RadioSelect
            )

    @property
    def rows(self):
        return [
            {
                "participation": p,
                "role": self[f"role_{p.player_id}"],
                "info": self[f"info_{p.player_id}"],
            }
            for p in self.participations
        ]

    @property
    def finishing(self) -> bool:
        return self.data.get("action") == self.FINISH or self.game.ended_at is not None

    def clean(self):
        data = super().clean()
        if not self.finishing:
            return data
        roles = [data.get(f"role_{p.player_id}") for p in self.participations]
        if len(roles) < 2:
            raise forms.ValidationError("Il faut au moins deux joueurs pour terminer une partie.")
        if Role.VILLAIN not in roles or Role.KIND not in roles:
            raise forms.ValidationError("Il faut au moins un gentil et un méchant.")
        if not data.get("winner_role"):
            self.add_error("winner_role", "Choisis le camp gagnant.")
        awards = [data.get(f"info_{p.player_id}") for p in self.participations]
        if awards.count(Award.BEST) > 1:
            raise forms.ValidationError("Un seul « meilleur joueur » par partie.")
        if awards.count(Award.WORST) > 1:
            raise forms.ValidationError("Un seul « pire joueur » par partie.")
        return data

    @transaction.atomic
    def save(self) -> Game:
        data = self.cleaned_data
        game = self.game
        for p in self.participations:
            p.role = data[f"role_{p.player_id}"]
            p.info = data[f"info_{p.player_id}"]
            p.save(update_fields=["role", "info"])

        new_start = data.get("started_at")
        if new_start and game.started_at and new_start != game.started_at:
            # on décale la fin du même écart pour conserver la durée
            if game.ended_at:
                game.ended_at += new_start - game.started_at
            game.started_at = new_start
        game.started_at = game.started_at or timezone.now()

        if data.get("winner_role"):
            game.winner_role = data["winner_role"]
        if self.finishing and not game.ended_at:
            now = timezone.now()
            # partie saisie après coup (date ancienne) : durée inconnue plutôt que fausse
            backfilled = now - game.started_at > timedelta(hours=3)
            game.ended_at = game.started_at if backfilled else max(now, game.started_at)
        game.save()
        return game
