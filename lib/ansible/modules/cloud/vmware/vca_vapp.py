#!/usr/bin/python

# Copyright (c) 2015 Ansible, Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: vca_vapp
short_description: Manages vCloud Air vApp instances.
description:
  - This module will actively managed vCloud Air vApp instances.  Instances
    can be created and deleted as well as both deployed and undeployed.
version_added: "2.0"
author: Peter Sprygada (@privateip)
options:
  vapp_name:
    description:
      - The name of the vCloud Air vApp instance
    required: yes
  template_name:
    description:
      - The name of the vApp template to use to create the vApp instance.  If
        the I(state) is not `absent` then the I(template_name) value must be
        provided.  The I(template_name) must be previously uploaded to the
        catalog specified by I(catalog_name)
    required: no
    default: None
  network_name:
    description:
      - The name of the network that should be attached to the virtual machine
        in the vApp.  The virtual network specified must already be created in
        the vCloud Air VDC.  If the I(state) is not 'absent' then the
        I(network_name) argument must be provided.
    required: no
    default: None
  network_mode:
    description:
      - Configures the mode of the network connection.
    required: no
    default: pool
    choices: ['pool', 'dhcp', 'static']
  vm_name:
    description:
      - The name of the virtual machine instance in the vApp to manage.
    required: no
    default: None
  vm_cpus:
    description:
      - The number of vCPUs to configure for the VM in the vApp.   If the
        I(vm_name) argument is provided, then this becomes a per VM setting
        otherwise it is applied to all VMs in the vApp.
    required: no
    default: None
  vm_memory:
    description:
      - The amount of memory in MB to allocate to VMs in the vApp.  If the
        I(vm_name) argument is provided, then this becomes a per VM setting
        otherise it is applied to all VMs in the vApp.
    required: no
    default: None
  operation:
    description:
      - Specifies an operation to be performed on the vApp.
    required: no
    default: noop
    choices: ['noop', 'poweron', 'poweroff', 'suspend', 'shutdown', 'reboot', 'reset']
  state:
    description:
      - Configures the state of the vApp.
    required: no
    default: present
    choices: ['present', 'absent', 'deployed', 'undeployed']
  username:
    description:
      - The vCloud Air username to use during authentication
    required: false
    default: None
  password:
    description:
      - The vCloud Air password to use during authentication
    required: false
    default: None
  org:
    description:
      - The org to login to for creating vapp, mostly set when the service_type is vdc.
    required: false
    default: None
  instance_id:
    description:
      - The instance id in a vchs environment to be used for creating the vapp
    required: false
    default: None
  host:
    description:
      - The authentication host to be used when service type  is vcd.
    required: false
    default: None
  api_version:
    description:
      - The api version to be used with the vca
    required: false
    default: "5.7"
  service_type:
    description:
      - The type of service we are authenticating against
    required: false
    default: vca
    choices: [ "vca", "vchs", "vcd" ]
  vdc_name:
    description:
      - The name of the virtual data center (VDC) where the vm should be created or contains the vAPP.
    required: false
    default: None
'''

EXAMPLES = '''

- name: Creates a new vApp in a VCA instance
  vca_vapp:
    vapp_name: tower
    state: present
    template_name: 'Ubuntu Server 12.04 LTS (amd64 20150127)'
    vdc_name: VDC1
    instance_id: '<your instance id here>'
    username: '<your username here>'
    password: '<your password here>'

'''

from ansible.module_utils.vca import VcaAnsibleModule, VcaError


DEFAULT_VAPP_OPERATION = 'noop'

VAPP_STATUS = {
    'Powered off': 'poweroff',
    'Powered on': 'poweron',
    'Suspended': 'suspend'
}

VAPP_STATES = ['present', 'absent', 'deployed', 'undeployed']
VAPP_OPERATIONS = ['poweron', 'poweroff', 'suspend', 'shutdown',
                   'reboot', 'reset', 'noop', 'connectnetwork']


def get_instance(module):
    vapp_name = module.params['vapp_name']
    inst = dict(vapp_name=vapp_name, state='absent')
    try:
        vapp = module.get_vapp(vapp_name)
        if vapp:
            status = module.vca.get_status(vapp.me.get_status())
            inst['status'] = VAPP_STATUS.get(status, 'unknown')
            inst['state'] = 'deployed' if vapp.me.deployed else 'undeployed'
        return inst
    except VcaError:
        return inst

def create(module):
    vdc_name = module.params['vdc_name']
    vapp_name = module.params['vapp_name']
    template_name = module.params['template_name']
    catalog_name = module.params['catalog_name']
    network_name = module.params['network_name']
    network_mode = module.params['network_mode']
    vm_name = module.params['vm_name']
    vm_cpus = module.params['vm_cpus']
    vm_memory = module.params['vm_memory']
    deploy = module.params['state'] == 'deploy'
    poweron = module.params['operation'] == 'poweron'
    connectnetwork = module.params['operation'] == 'connectnetwork'

    task = module.vca.create_vapp(vdc_name, vapp_name, template_name,
                                  catalog_name, network_name, network_mode,
                                  vm_name, vm_cpus, vm_memory, deploy, poweron)
    if task is False:
        module.fail('unable to create vapp')

    if task is False:
        module.fail('Failed to create vapp: ' + vapp_name)

    module.vca.block_until_completed(task)

    # Connect the network to the Vapp/VM and return asigned IP
    #if (module.params['operation'] == 'connectnetwork'):
    if (network_name != None):
            vm_ip = connect_to_network(module, vdc_name, vapp_name, network_name, network_mode)
            return vm_ip


def delete(module):
    vdc_name = module.params['vdc_name']
    vapp_name = module.params['vapp_name']
    module.vca.delete_vapp(vdc_name, vapp_name)

def do_operation(module):
    vapp_name = module.params['vapp_name']
    operation = module.params['operation']

    vm_name = module.params.get('vm_name')
    vm = None
    if vm_name:
        vm = module.get_vm(vapp_name, vm_name)

    if operation == 'poweron':
        operation = 'powerOn'
    elif operation == 'poweroff':
        operation = 'powerOff'

    cmd = 'power:%s' % operation
    module.get_vapp(vapp_name).execute(cmd, 'post', targetVM=vm)

def set_state(module):
    state = module.params['state']
    vapp = module.get_vapp(module.params['vapp_name'])
    if state == 'deployed':
        action = module.params['operation'] == 'poweron'
        if not vapp.deploy(action):
            module.fail('unable to deploy vapp')
    elif state == 'undeployed':
        action = module.params['operation']
        if action == 'poweroff':
            action = 'powerOff'
        elif action != 'suspend':
            action = None
        if not vapp.undeploy(action):
            module.fail('unable to undeploy vapp')

def connect_to_network(module, vdc_name, vapp_name, network_name, network_mode):

    nets = filter(lambda n: n.name == network_name, module.vca.get_networks(vdc_name))
    assert len(nets) == 1
    the_vdc = module.vca.get_vdc(vdc_name)
    the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
    assert the_vapp
    assert the_vapp.name == vapp_name

    # Connect vApp
    task = the_vapp.connect_to_network(nets[0].name, nets[0].href)
    result = module.vca.block_until_completed(task)
    assert result

    # Connect VM
    if(network_mode == 'pool'):
        task = the_vapp.connect_vms(nets[0].name, connection_index=0, ip_allocation_mode='POOL')
    else:
        if(network_mode == 'dhcp'):
            task = the_vapp.connect_vms(nets[0].name, connection_index=0, ip_allocation_mode='DHCP')

    assert task
    result = module.vca.block_until_completed(task)
    assert result

    #Update VApp info and get VM IP
    the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
    assert the_vapp

    return get_vm_details(module)

def get_vm_details(module):
    vdc_name = module.params['vdc_name']
    vapp_name = module.params['vapp_name']
    vm_name = module.params['vm_name']
    the_vdc = module.vca.get_vdc(vdc_name)
    the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
    assert the_vapp
    assert the_vapp.name == vapp_name
    the_vm_details = dict()

    for vm in the_vapp.me.Children.Vm:
        sections = vm.get_Section()

        customization_section = (
            filter(lambda section:
                   section.__class__.__name__ ==
                   "GuestCustomizationSectionType",
                   sections)[0])
        if customization_section.get_AdminPasswordEnabled():
            the_vm_details["vm_admin_password"] = customization_section.get_AdminPassword()

        virtualHardwareSection = (
            filter(lambda section:
                   section.__class__.__name__ ==
                   "VirtualHardwareSection_Type",
                   sections)[0])
        items = virtualHardwareSection.get_Item()
        ips = []
        _url = '{http://www.vmware.com/vcloud/v1.5}ipAddress'
        for item in items:
            if item.Connection:
                for c in item.Connection:
                    if c.anyAttributes_.get(
                            _url):
                        ips.append(c.anyAttributes_.get(
                            _url))
    if len(ips) > 0:
        the_vm_details["vm_ip"] = ips[0]

    return the_vm_details

def main():

    argument_spec = dict(
        vapp_name=dict(required=True),
        vdc_name=dict(required=True),
        template_name=dict(),
        catalog_name=dict(default='Public Catalog'),
        network_name=dict(),
        network_mode=dict(default='pool', choices=['dhcp', 'static', 'pool']),
        network_interface=dict(type='int', default=0),
        vm_ip=dict(),
        vm_name=dict(),
        vm_cpus=dict(type='int'),
        vm_memory=dict(type='int'),
        operation=dict(default=DEFAULT_VAPP_OPERATION, choices=VAPP_OPERATIONS),
        state=dict(default='present', choices=VAPP_STATES),
        verify_certs=dict(type='bool', default=True),
        pyvcloud_log=dict(type='bool', default=False)

    )

    module = VcaAnsibleModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    state = module.params['state']
    operation = module.params['operation']

    instance = get_instance(module)

    result = dict(changed=False)

    if instance and state == 'absent':
        if not module.check_mode:
            delete(module)
        result['changed'] = True

    elif state != 'absent':
        if instance['state'] == 'absent':
            if not module.check_mode:
                result['ansible_facts'] = create(module)
            result['changed'] = True

        elif instance['state'] != state and state != 'present':
            if not module.check_mode:
                set_state(module)
            result['changed'] = True

        if operation != instance.get('status') and operation != 'noop':
            if not module.check_mode:
                do_operation(module)
            result['changed'] = True
        result['ansible_facts'] = get_vm_details(module)

    return module.exit(**result)


if __name__ == '__main__':
    main()
