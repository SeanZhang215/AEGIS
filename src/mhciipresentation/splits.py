#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""splits.py

This script generates different train, test and validation splits for the
various datasets used in the mhciipresentation project containing data coming
from single allele, eluted peptides as well as randomly sampled peptides as
achieved by Nielsen and colleagues in:
https://academic.oup.com/nar/article/48/W1/W449/5837056
"""

import os
import random
from typing import Set

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from mhciipresentation.constants import N_MOTIF_FOLDS
from mhciipresentation.human.human import load_raw_files, select_data_files
from mhciipresentation.loaders import (
    load_public_mouse_data,
    load_sa_data,
    load_sa_el_data,
)
from mhciipresentation.paths import LEVENSTEIN_DIR, RAW_DATA, SPLITS_DIR
from mhciipresentation.utils import make_dir


def remove_overlapping_peptides(
    peptides_1: Set, peptides_2: Set,
) -> pd.Series:
    """Removes peptides occuring in peptides_2 from peptides_1

    Args:
        peptides_1 (np.ndarray): peptides to remove from
        peptides_2 (np.ndarray): peptides to check against

    Returns:
        pd.Series: peptides_1, which does not contain elements present in
            peptides_2
    """
    # Creates a difference between two sets to get the duplicate peptides as
    # fast as possible
    peptides_1_reduced = peptides_1.difference(peptides_2)

    # Remove features and labels that correspond to duplicate peptides
    return peptides_1_reduced, peptides_2


def validate_split(
    X_train: np.ndarray, X_val: np.ndarray, X_test: np.ndarray = None
) -> None:
    """Validates the splits by checking absence of overlap of peptides among
        splits

    Args:
        X_train (np.ndarray): training features
        X_val (np.ndarray): validation features
        X_test (np.ndarray): testing features
    """

    print(
        f"Overlap between train and val"
        f" {len(set(X_train).intersection(set(X_val)))}"
    )
    if X_test is not None:
        print(
            f"Overlap between train and test"
            f" {len(set(X_train).intersection(set(X_test)))}"
        )

        print(
            f"Overlap between val and test"
            f" {len(set(X_val).intersection(set(X_test)))}"
        )


def save_idx(
    out_dir: str,
    X_train_data: pd.DataFrame,
    X_val_data: pd.DataFrame,
    X_test_data: pd.DataFrame = None,
) -> None:
    X_train_data.index.to_frame(name="index").to_csv(
        out_dir + "X_train_idx.csv", index=False
    )
    X_val_data.index.to_frame(name="index").to_csv(
        out_dir + "X_val_idx.csv", index=False
    )
    if X_test_data is not None:
        X_test_data.index.to_frame(name="index").to_csv(
            out_dir + "X_test_idx.csv", index=False
        )


def label_dist_summary(
    data: pd.DataFrame, target_col: str, dataset_name: str
) -> None:
    value_cts = data[target_col].value_counts()
    print(
        f"Label distribution in {dataset_name}: negative samples = "
        f" {value_cts[0]}; positive samples = {value_cts[1]}"
    )


def random_splitting(
    data: pd.DataFrame,
    out_dir: str = SPLITS_DIR + "/random/",
    eval_frac: float = 0.2,
    val_frac: float = 0.5,
) -> None:
    """Randomly splits the data and saves the resulting indices under SPLITS_DIR
        + "/random/".

    Args:
        data (pd.DataFrame): input dataset
        out_dir (str): output directory
        eval_frac (float): fraction of the total dataset used for evaluation
            (i.e. validation and testing)
        val_frac (float): fraction of the evaluation set used for validation
    """
    # *_tmp contains the data from all evaludation sets (validation + test sets)
    X_train, X_eval, y_train, y_eval = train_test_split(
        data.peptide.values,
        data.target_value.values,
        test_size=eval_frac,
        random_state=42,
    )

    # Remove peptides occuring in the test set from training set
    X_train, X_eval = remove_overlapping_peptides(set(X_train), set(X_eval))
    X_train_data = data[data["peptide"].isin(X_train)]
    X_eval_data = data[data["peptide"].isin(X_eval)]

    # Generate dev and validation set from test set
    X_val = X_eval_data.sample(frac=val_frac, random_state=42).peptide
    X_test = X_eval_data.drop(X_val.index).peptide

    # Remove peptides occuring in validation set from test set
    if X_test.shape[0] != 0:
        X_test, X_val = remove_overlapping_peptides(set(X_val), set(X_test))
        X_test_data = data[data["peptide"].isin(X_test)]
    else:
        X_test_data = None

    X_val_data = data[data["peptide"].isin(X_val)]

    if X_test_data is not None:
        validate_split(
            X_train_data.peptide, X_val_data.peptide, X_test_data.peptide
        )
    else:
        validate_split(
            X_train_data.peptide, X_val_data.peptide,
        )

    # Summary of samples sizes
    label_dist_summary(X_train_data, "target_value", "training")
    label_dist_summary(X_val_data, "target_value", "validation")
    if X_test_data is not None:
        label_dist_summary(X_test_data, "target_value", "testing")

    # Writing the data
    make_dir(out_dir)

    save_idx(out_dir, X_train_data, X_val_data, X_test_data)
    print("Written random splits successfully")


def random_splitting_mouse(data: pd.DataFrame) -> None:
    """We stratify by protein name.

    Args:
        data (pd.DataFrame): dataset to stratify
    """
    unique_proteins = set(
        data.loc[data.label == 1]["Uniprot Accession"].to_list()
    )
    val_proteins = set(
        random.sample(unique_proteins, int(len(unique_proteins) * 0.1))
    )
    test_proteins = set(
        random.sample(
            unique_proteins - val_proteins, int(len(unique_proteins) * 0.1)
        )
    )
    train_proteins = unique_proteins - test_proteins.union(val_proteins)

    X_train_data = data.loc[data["Uniprot Accession"].isin(train_proteins)]
    X_val_data = data.loc[data["Uniprot Accession"].isin(val_proteins)]
    X_test_data = data.loc[data["Uniprot Accession"].isin(test_proteins)]

    X_train_data_neg = data.loc[data.label == 0].sample(len(X_train_data) * 5)
    data = data.loc[data.label == 0].loc[
        ~data["Peptide Sequence"].isin(
            set(X_train_data_neg["Peptide Sequence"].to_list())
        )
    ]
    X_val_data_neg = data.loc[data.label == 0].sample(len(X_val_data) * 5)
    data = data.loc[data.label == 0].loc[
        ~data["Peptide Sequence"].isin(
            set(X_val_data_neg["Peptide Sequence"].to_list()).union(
                set(X_train_data_neg["Peptide Sequence"].to_list())
            )
        )
    ]
    X_test_data_neg = data.loc[data.label == 0].sample(len(X_test_data) * 5)

    X_train_data = X_train_data.append(X_train_data_neg)
    X_val_data = X_val_data.append(X_val_data_neg)
    X_test_data = X_test_data.append(X_test_data_neg)

    # Summary of samples sizes
    label_dist_summary(X_train_data, "label", "training")
    label_dist_summary(X_val_data, "label", "validation")
    label_dist_summary(X_test_data, "label", "testing")

    # Writing the data
    out_dir = SPLITS_DIR + "/mouse/" + "/random/"
    make_dir(out_dir)
    save_idx(out_dir, X_train_data, X_val_data, X_test_data)
    X_train_data.to_csv(out_dir + "X_train.csv", index=False)
    X_val_data.to_csv(out_dir + "X_val.csv", index=False)
    X_test_data.to_csv(out_dir + "X_test.csv", index=False)
    print("Written random splits successfully")


def motif_exclusion(data: pd.DataFrame) -> None:
    list_of_peptide_files = select_data_files(os.listdir(RAW_DATA))
    list_of_peptide_files.sort()
    raw_files = load_raw_files(list_of_peptide_files)
    data_with_filename = data.merge(
        raw_files[["peptide", "file_name"]].drop_duplicates(),
        how="left",
        on="peptide",
    )

    motifs_splits_dir = SPLITS_DIR + "/motifs/"
    make_dir(motifs_splits_dir)

    for i in range(N_MOTIF_FOLDS):
        X_train = data_with_filename.loc[
            data_with_filename.file_name == f"train_EL{i+1}.txt"
        ]
        X_train = data.loc[data.peptide.isin(X_train.peptide.tolist())]

        X_val = data_with_filename.loc[
            data_with_filename.file_name == f"test_EL{i+1}.txt"
        ]
        X_val = data.loc[data.peptide.isin(X_val.peptide.tolist())]
        label_dist_summary(X_train, "target_value", "training")
        label_dist_summary(X_val, "target_value", "validation")
        validate_split(X_train.peptide, X_val.peptide)
        out_dir = motifs_splits_dir + f"/split_{i+1}/"
        make_dir(out_dir)
        save_idx(out_dir, X_train, X_val)
        print(f"Done with split {i+1}")


def leventstein(data: pd.DataFrame) -> None:
    """Split data according

    Args:
        data (pd.DataFrame): [description]
    """
    pos_groups = pd.read_csv(LEVENSTEIN_DIR + "pos_pep_lev_groups.csv")
    pos_groups = pos_groups.sample(frac=1)
    lev_groups = pos_groups["lev_group"].drop_duplicates()

    lev_group_train = lev_groups.sample(frac=0.8, replace=False)
    lev_group_eval = lev_groups.drop(lev_group_train.index)
    lev_group_val = lev_group_eval.sample(frac=0.5, replace=False)
    lev_group_test = lev_group_eval.drop(lev_group_val.index)

    data = data.merge(pos_groups, on="peptide", how="left")
    positive_peptides_train = data.loc[
        data["lev_group"].isin(lev_group_train.tolist())
    ].drop(columns=["lev_group"])
    positive_peptides_val = data.loc[
        data["lev_group"].isin(lev_group_val.tolist())
    ].drop(columns=["lev_group"])
    positive_peptides_test = data.loc[
        data["lev_group"].isin(lev_group_test.tolist())
    ].drop(columns=["lev_group"])

    # Negative data are not "grouped" as much, so we can randomly split them.
    negative_data = data.loc[data["target_value"] == 0.0]

    neg_X_train, neg_X_eval, _, _ = train_test_split(
        negative_data.peptide.values,
        negative_data.target_value.values,
        test_size=0.2,
        random_state=42,
    )

    # Remove peptides occuring in the test set from training set
    neg_X_train, neg_X_eval = remove_overlapping_peptides(
        set(neg_X_train), set(neg_X_eval)
    )
    negative_peptides_train = data[data["peptide"].isin(neg_X_train)]
    X_eval_data = data[data["peptide"].isin(neg_X_eval)]

    # Generate dev and validation set from test set
    X_val = X_eval_data.sample(frac=0.5, random_state=42)
    X_test = X_eval_data.drop(X_val.index)

    # Remove peptides occuring in validation set from test set
    X_test, X_val = remove_overlapping_peptides(
        set(X_test.peptide), set(X_val.peptide)
    )
    negative_peptides_val = data[data["peptide"].isin(X_val)]
    negative_peptides_test = data[data["peptide"].isin(X_test)]

    # Merge negative data with positive data separated by lev groups
    train_data = positive_peptides_train.append(negative_peptides_train)
    val_data = positive_peptides_val.append(negative_peptides_val)
    test_data = positive_peptides_test.append(negative_peptides_test)
    validate_split(train_data.peptide, val_data.peptide, test_data.peptide)

    # Summary of samples sizes
    label_dist_summary(train_data, "target_value", "training")
    label_dist_summary(val_data, "target_value", "validation")
    label_dist_summary(test_data, "target_value", "testing")

    # Writing the data
    out_dir = SPLITS_DIR + "/levenstein/"
    make_dir(out_dir)
    save_idx(out_dir, train_data, val_data, test_data)
    print("Written random splits successfully")


def main():
    # print("Splitting public dataset")
    # sa_el_data = load_sa_el_data()
    # print("Random splitting of human data")
    # random_splitting(sa_el_data)
    # print("Motif exclusion splitting of human data")
    # motif_exclusion(sa_el_data)
    # print("Levenstein splitting of human data")
    # leventstein(sa_el_data)

    # print("Splitting SA EL + BA data randomly")
    # sa_data = load_sa_data()
    # random_splitting(
    #     sa_data,
    #     out_dir=SPLITS_DIR + "/random_sa/",
    #     val_frac=1,
    #     eval_frac=0.01,
    # )

    print("Random splitting of mouse data")
    mouse_data = load_public_mouse_data()
    random_splitting_mouse(mouse_data)


if __name__ == "__main__":
    main()