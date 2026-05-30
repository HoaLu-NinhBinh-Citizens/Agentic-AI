
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Bug: data leakage
scaler = StandardScaler()
X_scaled = scaler.fit(X)  # Should be after split

X_train, X_test, y_train, y_test = train_test_split(X, y)
