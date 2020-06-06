"""
Light Brightness Automation

Sets light brightness based on input_select.<light>_mode value.
    Automatic: Sets brightness based on time-of-day
    Maximum: 100% or per-light max defined in config
    Minimum: 10% or per-light min defined in config
    Manual: Not controlled by automation

When a light is turned off for a certain period of time, the mode will revert to 'Automatic'.
This allows lights to always turn on with the time-of-day brightness.
"""

import appdaemon.plugins.hass.hassapi as hass
import datetime


class LightBrightness(hass.Hass):

    def initialize(self):

        # Loop through the entities
        for entity in self.args["entities"]:
            # Add details to entity dict
            entity['zwave'] = 'zwave.{}'.format(entity['name'])
            entity['light'] = 'light.{}'.format(entity['name'])
            entity['friendly'] = self.friendly_name(entity['light'])
            entity['mode'] = 'input_select.{}_mode'.format(entity['name'])
            entity['setpoint'] = 'input_number.{}_last_setpoint'.format(
                entity['name'])
            entity['on_threshold'] = entity.get(
                'on_threshold', self.args['defaults']['on_threshold'])
            entity['off_threshold'] = entity.get(
                'off_threshold', self.args['defaults']['off_threshold'])
            entity['min_brightness'] = entity.get(
                'min_brightness', self.args['defaults']['min_brightness'])
            entity['max_brightness'] = entity.get(
                'max_brightness', self.args['defaults']['max_brightness'])
            entity['brightness_schedule'] = entity.get(
                'brightness_schedule', self.args['defaults']['brightness_schedule'])

            # Check if the light is on or off at init, arm the appropriate callback
            state = self.get_state(entity['light'])
            if state == 'on':
                self.listen_state(
                    self.turned_off_callback,
                    entity=entity['light'],
                    entity_dict=entity,
                    new='off',
                    oneshot=True
                )
            elif state == 'off':
                self.listen_state(
                    self.turned_on_callback,
                    entity=entity['light'],
                    entity_dict=entity,
                    new='on',
                    oneshot=True
                )

            # Arm the turned_on_callback after light has been off for a set duration
            self.listen_state(
                callback=self.arm_callback,
                entity=entity['light'],
                entity_dict=entity,
                new='off',
                duration=entity['off_threshold'],
                target_callback='turned_on_callback',
            )

            # Arm the turned_off_callback after light has been on for a set duration
            self.listen_state(
                callback=self.arm_callback,
                entity=entity['light'],
                entity_dict=entity,
                new='on',
                duration=entity['on_threshold'],
                target_callback='turned_off_callback',
            )

            # Set auto-brightness every 5 minutes if light is on and mode is Automatic
            self.run_every(
                callback=self.auto_brightness_callback,
                start=datetime.datetime.now() + datetime.timedelta(seconds=1),
                interval=300,
                entity_dict=entity,
                transition=300,
                check_current_brightness=True
            )

            # Listen for mode dropdown changes
            self.listen_state(
                callback=self.mode_changed_callback,
                entity=entity['mode'],
                entity_dict=entity
            )

    def mode_changed_callback(self, entity, attribute, old, new, kwargs):
        """ Set brightness based on the new selected mode. """

        entity_dict = kwargs['entity_dict']
        self.log('{} mode changed to {}.'.format(entity_dict['friendly'], new))

        if new == 'Maximum':
            self.turn_on(entity_dict['light'],
                         brightness_pct=entity_dict['max_brightness'])
            self.log('Setting {} to {}% brightness.'.format(
                entity_dict['friendly'], entity_dict['max_brightness']))
        elif new == 'Minimum':
            self.turn_on(entity_dict['light'],
                         brightness_pct=entity_dict['min_brightness'])
            self.log('Setting {} to {}% brightness.'.format(
                entity_dict['friendly'], entity_dict['min_brightness']))
        elif new == 'Automatic':
            self.set_value(entity_dict['setpoint'], value=0)
            self.auto_brightness_callback(
                dict(entity_dict=entity_dict))

    def turned_on_callback(self, entity, attribute, old, new, kwargs):
        """ Sets brightness immediately if mode is set to 'Automatic' """

        entity_dict = kwargs['entity_dict']
        self.auto_brightness_callback(
            dict(entity_dict=entity_dict))

    def turned_off_callback(self, entity, attribute, old, new, kwargs):
        """ Sets mode back to 'Automatic' when light has been off for a set duration. """

        entity_dict = kwargs['entity_dict']
        self.log('{} turned off, setting mode to Automatic and resetting last setpoint.'.format(
            entity_dict['friendly']))

        self.set_value(entity_dict['setpoint'], 0)
        self.select_option(entity_dict['mode'], 'Automatic')

    def arm_callback(self, entity, attribute, old, new, kwargs):
        """ 
        Used to arm the turned_off and turned_on callbacks after a delay. 
        Works around buggy reporting/flip-flopping from GE switches during on/off transition. 
        """

        entity_dict = kwargs['entity_dict']
        target_callback = kwargs.get('target_callback')

        if target_callback == 'turned_on_callback':
            # Wait for the light to get turned on, trigger immediately
            self.listen_state(
                callback=self.turned_on_callback,
                entity_dict=entity_dict,
                new='on',
                oneshot=True
            )
        elif target_callback == "turned_off_callback":
            # Wait for the light to get turned off, trigger immediately
            self.listen_state(
                callback=self.turned_off_callback,
                entity_dict=entity_dict,
                new='off',
                oneshot=True
            )

    def auto_brightness_callback(self, kwargs):
        """ Callback used to calculate and set brightness based on time-of-day light schedule. """

        entity_dict = kwargs['entity_dict']
        immediate = kwargs.get('immediate')
        transition = kwargs.get('transition', 0)
        check_current_brightness = kwargs.get(
            'check_current_brightness', False)
        ignore_state = kwargs.get('ignore_state')

        now = datetime.datetime.now()
        current_mode = self.get_state(entity_dict['mode'])
        state = self.get_state(entity_dict['light'])
        min_brightness = entity_dict['min_brightness']
        max_brightness = entity_dict['max_brightness']

        if current_mode != 'Automatic':
            return

        if state == 'off' and not ignore_state:
            return

        if check_current_brightness:
            current_brightness = self.get_state(
                entity_dict['light'], attribute='brightness')
            if not current_brightness:
                current_brightness = 0
            current_brightness_pct = current_brightness / 2.55

        # Iterate over the schedule, determine the brightness to use
        schedule = entity_dict['brightness_schedule']
        for i in range(len(schedule)):
            # Get the next schedule item, go to 0 (wrap around) if we're on the last schedule
            if i+1 == len(schedule):
                next_schedule = schedule[0]
            else:
                next_schedule = schedule[i+1]

            # Replace strings max/min_brightness with percents
            if next_schedule['pct'] == 'max_brightness':
                next_schedule_pct = max_brightness
            elif next_schedule['pct'] == 'min_brightness':
                next_schedule_pct = min_brightness
            else:
                next_schedule_pct = next_schedule['pct']

            if schedule[i]['pct'] == 'max_brightness':
                this_schedule_pct = max_brightness
            elif schedule[i]['pct'] == 'min_brightness':
                this_schedule_pct = min_brightness
            else:
                this_schedule_pct = schedule[i]['pct']

            # Determine if now is during or between two schedules
            in_schedule = self.timestr_delta(
                schedule[i]['start'], now, schedule[i]['end'])
            between_schedule = self.timestr_delta(
                schedule[i]['end'], now, next_schedule['start'])

            if in_schedule['now_is_between']:
                # If we're within a schedule entry's time window, match exactly
                target_percent = round(this_schedule_pct)
                transition = 0

                # don't eval any ore schedules
                break
            elif between_schedule['now_is_between']:
                # if we are between two schedules, calculate the brightness percentage
                time_diff = between_schedule['start_to_end'].total_seconds()
                bright_diff = this_schedule_pct - next_schedule_pct
                bright_per_second = bright_diff / time_diff

                if immediate:
                    # If setting an immediate brightness, we want to calculate the brightness percentage and then make a recursive call
                    target_percent = round(this_schedule_pct -
                                           (between_schedule['since_start'].total_seconds(
                                           ) * bright_per_second))
                    transition = 0
                    self.run_in(
                        self.auto_brightness_callback,
                        delay=5,
                        entity_dict=entity_dict,
                        transition=295
                    )
                else:
                    if between_schedule['to_end'].total_seconds() <= transition:
                        # If we're in a new schedule in the next 5 minutes, use that schedule's brightness
                        target_percent = round(next_schedule_pct)
                        transition = between_schedule['to_end'].total_seconds(
                        )
                    else:
                        target_percent = round(this_schedule_pct -
                                               ((between_schedule['since_start'].total_seconds(
                                               ) + transition) * bright_per_second))

                # don't eval any more schedules
                break

        # set brightness if a schedule was matched and the percent has changed since the last auto-brightness run
        # Don't change if the brightness was changed from another source (at the switch, hass ui, google assistant, etc.)
        if target_percent:
            last_percent = round(
                float(self.get_state(entity_dict['setpoint'])))
            if last_percent != target_percent:
                if check_current_brightness and abs(last_percent - current_brightness_pct) > 5:
                    self.log(
                        '{}: Brightness changed manually, not moving.'.format(entity_dict['friendly']))
                    self.select_option(entity_dict['mode'], 'Manual')
                else:
                    self.log("Setting {} to auto-brightness - {}% over {} seconds".format(
                        entity_dict['friendly'], round(target_percent, 2), transition))
                    self.turn_on(
                        entity_id=entity_dict['light'],
                        brightness_pct=target_percent,
                        transition=transition
                    )
                    self.set_value(
                        entity_dict['setpoint'], round(target_percent))

    def timestr_delta(self, start_time_str, now, end_time_str, name=None):
        """ Helper function for calculating time deltas between schedule entries. """

        start_time = self.parse_time(start_time_str, name)
        end_time = self.parse_time(end_time_str, name)

        start_date = now.replace(
            hour=start_time.hour, minute=start_time.minute,
            second=start_time.second
        )
        end_date = now.replace(
            hour=end_time.hour, minute=end_time.minute, second=end_time.second
        )
        if end_date < start_date:
            # Spans midnight
            if now < start_date and now < end_date:
                now = now + datetime.timedelta(days=1)
            end_date = end_date + datetime.timedelta(days=1)
        return {
            "now_is_between": (start_date <= now <= end_date),
            "start_to_end": (end_date - start_date),
            "since_start": (now - start_date),
            "to_end": (end_date - now),
            "start_date": start_date,
            "end_date": end_date
        }
