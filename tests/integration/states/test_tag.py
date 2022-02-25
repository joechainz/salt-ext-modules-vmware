# Copyright 2021 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
import pytest
import saltext.vmware.modules.tag as tagging
import saltext.vmware.states.tag as tagging_state


def test_manage_create(patch_salt_globals_tag_state, patch_salt_globals_tag, vmware_tag_name_c):
    """
    test tag manage create
    """
    tag_name, cat_id = vmware_tag_name_c
    res = tagging_state.present(
        tag_name,
        description="testing state tag create",
        category_id=cat_id,
    )
    assert "created" in res["comment"]


def test_manage_update(patch_salt_globals_tag_state, vmware_tag):
    """
    test tag manage update
    """

    res = tagging_state.present("test-tag", description="new discription")
    assert "updated" in res["comment"]


def test_manage_delete(patch_salt_globals_tag_state, vmware_category):
    """
    test tag manage delete
    """
    res = tagging_state.present(
        "state tag",
        description="testing state tag create",
        category_id=vmware_category,
    )
    res = tagging_state.absent("state tag")
    assert "deleted" in res["comment"]


def test_manage_create_cat_test(patch_salt_globals_tag_state_test):
    """
    test category manage create test = true
    """
    res = tagging_state.present_category("state test cat", ["string"], "SINGLE", "test category")
    assert "state test cat category will be created" in res["comment"]


def test_manage_create_cat(patch_salt_globals_tag_state, vmware_cat_name_c):
    """
    test category manage create
    """
    res = tagging_state.present_category(vmware_cat_name_c, ["string"], "SINGLE", "test category")
    assert "created" in res["comment"]


def test_manage_update_cat_test(patch_salt_globals_tag_state_test, vmware_category):
    """
    test tag manage update test = true
    """

    res = tagging_state.present_category("test-cat", ["string"], "SINGLE", "new description")
    assert "test-cat category will be updated" in res["comment"]


def test_manage_update_cat(patch_salt_globals_tag_state, vmware_category):
    """
    test tag manage update
    """

    res = tagging_state.present_category("test-cat", ["string"], "SINGLE", "new description")
    assert "updated" in res["comment"]


def test_manage_delete_cat_test(patch_salt_globals_tag_state_test, vmware_category):
    """
    test tag manage delete test = true
    """
    res = tagging_state.absent_category("test-cat")
    assert "test-cat category will be deleted" in res["comment"]


def test_manage_delete_cat(patch_salt_globals_tag_state):
    """
    test tag manage delete
    """
    res = tagging_state.present_category("state test cat", ["string"], "SINGLE", "test category")
    res = tagging_state.absent_category("state test cat")
    assert "deleted" in res["comment"]
