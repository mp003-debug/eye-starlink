"""One text catalog for targets, baked UI and checked local speech assets."""
PRIMARY_KEYS=('water','rest','help')
RESPONSE_KEYS=('yes','no','please_stop')
CARE_KEYS=('reposition','toilet','unwell')
QUICK_KEYS=RESPONSE_KEYS+CARE_KEYS
PHRASE_TEXT={
    'water':'我想喝水', 'rest':'我想休息', 'help':'请来帮助我',
    'yes':'是', 'no':'不是', 'please_stop':'请停一下',
    'reposition':'请帮我换个姿势', 'toilet':'我要上厕所', 'unwell':'我不舒服',
}
PHRASE_LABELS={**PHRASE_TEXT,'reposition':'换个姿势','toilet':'上厕所'}
