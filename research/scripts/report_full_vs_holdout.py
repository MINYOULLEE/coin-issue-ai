import json, sys
import numpy as np
from sklearn.tree import DecisionTreeClassifier
sys.path.insert(0, str(__file__).rsplit('\\',1)[0])
import train_coin_answer as b

for s in sys.argv[1:]:
    j=json.load(open(f'research/results/{s.lower()}_walk_forward.json',encoding='utf-8'))
    _,it=b.dataset(s.upper()); t=np.array([z[0] for z in it]); x=np.array([z[1] for z in it]); f=np.array([z[2] for z in it])
    q=j['selected']; y=b.classify(f,q['neutral']); m=DecisionTreeClassifier(max_depth=q['depth'],min_samples_leaf=q['min_samples_leaf'],class_weight='balanced',random_state=42).fit(x,y)
    d,c=b.probabilities(m,x); z=b.simulate(t,f,d,c,q['low'],q['high'],q['exposures'])
    print(s.upper(), round(z['return_pct'],2), round(z['mdd_pct'],2), round(j['holdout']['return_pct'],2), round(j['holdout']['mdd_pct'],2))
