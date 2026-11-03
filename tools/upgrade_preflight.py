"""Read-only offline bundle checks and optional Linux ownership gate; no MMIO."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def owners():
    if ROOT.resolve()!=Path('/home/xilinx/Eye_Tracker_Upgrade_Version'):
        raise ValueError('upgrade ownership check requires the isolated board directory')
    for unit in ('eye-control.service','bootpy.service','clear_pl_statefile.service'):
        result=subprocess.run(['systemctl','show',unit,'--property=ActiveState','--value'],capture_output=True,text=True,check=True)
        if result.stdout.strip() not in ('inactive','failed'):raise ValueError('service owns or may reload PL: '+unit)
    result=subprocess.run(['fuser','/dev/mem'],capture_output=True,text=True)
    if result.returncode==0:raise ValueError('hardware memory is in use: '+result.stdout.strip())
    if result.returncode!=1:raise ValueError('hardware owner inspection failed: '+result.stderr.strip())
    return {'services_idle':True,'dev_mem_owners':[],'scope':'snapshot only; board CLI also holds shared baseline lock'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--owners',action='store_true');args=p.parse_args()
    if args.owners:
        print(json.dumps(owners()));return
    manifest=json.loads((ROOT/'upgrade_manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files'].items():
        path=(ROOT/name).resolve();path.relative_to(ROOT.resolve())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:raise ValueError('bundle mismatch: '+name)
    sys.path.insert(0,str(ROOT/'src'))
    from eye_tracker.launch import prepare_launch
    from eye_tracker.appearance_trial import VisualTrial
    from eye_tracker.audio import PhraseBank
    from eye_tracker.ui import BoardRenderer
    from eye_tracker.music import MusicLibrary
    plan=prepare_launch('data/private/profiles/upgrade_check.json',ROOT,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True,local_video=True,pastimes=True)
    profile=plan['profile_values'];trial=VisualTrial(ROOT/profile['model'],ROOT/profile['evidence'],ROOT)
    assert not trial.engine.baseline.samples
    bank=PhraseBank(include_quick=True);ui=BoardRenderer();music=MusicLibrary(ROOT/'assets/music',volume_path=ROOT/'data/private/music_volume.json')
    ui.bind_music(music)
    from eye_tracker.daily_tools import DailyTools
    daily=DailyTools.from_root(ROOT,local_video=True,pastimes=True);ui.bind_daily_tools(daily)
    print(json.dumps(dict(files_verified=len(manifest['files']),audio_phrases=len(bank.samples),ui_schema=ui.asset_metadata['version'],
                         initials_words=len(daily.words.words),initials_dictionary_sha256=daily.words.sha256,
                         audiobooks=daily.audiobook_library.provenance(),audiobook_saved_chapter=daily.bookmarks.selected,audiobook_saved_samples=[daily.bookmarks.position(i) for i in range(len(daily.audiobook_library.tracks))],bookmark_warning=daily.bookmarks.warning,
                         video=daily.video_library.provenance(),photos=len(daily.album.photos),pinyin_characters=len(daily.composer.lexicon.characters),favorites_count=len(daily.composer.favorites.items),music_tracks=len(music.tracks),music_volume_level=music.volume.level,emotion_cards=ui.asset_metadata['emotion_cards'],model_entry_consistent=True,fresh_reference_collected=False,hardware_loaded=False,wireless_enabled=False)))

if __name__=='__main__':main()
